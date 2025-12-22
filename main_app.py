import streamlit as st
import google.generativeai as genai 
import re
import datetime
import uuid
from groq import Groq
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 설정 및 공유 파라미터 확인 ---
st.set_page_config(page_title="한의사 임상 보조 시스템", page_icon="🩺", layout="centered")

# URL 주소창에 ?view=... 가 있는지 확인 (공유된 페이지 보기 모드)
query_params = st.query_params
shared_id = query_params.get("view")

# --- 2. 세션 상태 초기화 ---
if 'patient_info' not in st.session_state:
    st.session_state.patient_info = {"name": "", "gender": "미선택", "birth_year": ""}
if 'step' not in st.session_state:
    st.session_state.step = "input" 
if 'soap_result' not in st.session_state:
    st.session_state.soap_result = ""
if 'follow_up_questions' not in st.session_state:
    st.session_state.follow_up_questions = [] 
if 'raw_text' not in st.session_state:
    st.session_state.raw_text = ""
if 'additional_responses' not in st.session_state:
    st.session_state.additional_responses = {} 
if 'final_plan' not in st.session_state:
    st.session_state.final_plan = ""
if 'current_model' not in st.session_state:
    st.session_state.current_model = ""

# --- 3. [공유 페이지 모드] ID가 있을 경우 실행 ---
if shared_id:
    if 'db_storage' in st.session_state and shared_id in st.session_state.db_storage:
        data = st.session_state.db_storage[shared_id]
        st.markdown(f"### 🩺 {data['name']} 님의 진료 결과")
        st.info("이 페이지는 원장님으로부터 공유된 진료 기록입니다.")
        st.markdown('<div style="background-color: white; padding: 20px; border-radius: 15px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">', unsafe_allow_html=True)
        st.markdown(data['content'])
        
        # 혈자리 이미지 다시 표시
        img_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', data['content'], re.I)
        if img_patterns:
            st.divider()
            cols = st.columns(2)
            for idx, (name, url) in enumerate(img_patterns):
                with cols[idx % 2]:
                    st.image(url.strip(), use_container_width=True)
                    st.markdown(f"<div style='text-align:center; font-weight:700;'>{name}</div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.error("해당 진료 기록을 찾을 수 없거나 만료되었습니다.")
    
    if st.button("🏠 내 진료실 메인으로 이동"):
        st.query_params.clear()
        st.rerun()
    st.stop()

# --- 4. 기본 유틸리티 함수 ---
def calculate_age(birth_year):
    try:
        current_year = 2025
        return current_year - int(birth_year) + 1
    except: return "미상"

def clear_form():
    st.session_state.raw_text = ""
    st.session_state.patient_info = {"name": "", "gender": "미선택", "birth_year": ""}
    st.session_state.step = "input"
    st.session_state.soap_result = ""
    st.session_state.follow_up_questions = []
    st.session_state.additional_responses = {}
    st.session_state.final_plan = ""
    st.session_state.current_model = ""

# --- 5. 커스텀 CSS (원장님이 좋아하신 버튼 스타일) ---
st.markdown("""
    <style>
    .stCard { background-color: #ffffff; border-radius: 16px; padding: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; margin-bottom: 20px; }
    .q-item { background-color: #fefce8; border: 1px solid #fef08a; padding: 12px; border-radius: 10px; color: #854d0e; margin-top: 10px; font-weight: 500; }
    .acu-caption { font-size: 1.1rem !important; font-weight: 700 !important; color: #0f172a !important; text-align: center; margin-top: 5px; background: #f1f5f9; padding: 5px; border-radius: 5px; }
    div.stButton > button { border-radius: 15px !important; font-weight: 800 !important; transition: all 0.3s ease !important; }
    .main-btn > div > button { background-color: #2563eb !important; color: white !important; font-size: 1.3rem !important; height: 3.5em !important; box-shadow: 0 4px 15px rgba(37, 99, 235, 0.4) !important; }
    .verify-btn > div > button { background-color: #059669 !important; color: white !important; font-size: 1.3rem !important; height: 3.5em !important; box-shadow: 0 4px 15px rgba(5, 150, 105, 0.4) !important; }
    .share-btn > div > button { background-color: #f8fafc !important; color: #1e293b !important; border: 1px solid #e2e8f0 !important; height: 3em !important; }
    .model-badge { font-size: 0.8rem; background-color: #f1f5f9; color: #64748b; padding: 4px 12px; border-radius: 50px; font-weight: 600; margin-bottom: 5px; display: inline-block; border: 1px solid #e2e8f0; }
    </style>
    """, unsafe_allow_html=True)

# --- 6. API 및 분석 엔진 ---
api_keys = st.secrets.get("GEMINI_API_KEY", [])
if isinstance(api_keys, str): api_keys = [api_keys]
groq_client = None
try: groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])
except: pass
treatment_db_content = st.secrets.get("TREATMENT_DB", "DB 정보가 없습니다.")

def analyze_with_hybrid_fallback(prompt):
    models = ['models/gemini-2.0-flash-exp', 'models/gemini-1.5-flash']
    for api_key in api_keys:
        try:
            genai.configure(api_key=api_key)
            for m in models:
                try:
                    model = genai.GenerativeModel(m)
                    res = model.generate_content(prompt)
                    if res and res.text:
                        st.session_state.current_model = m.split('/')[-1]
                        return res.text
                except: continue
        except: continue
    return "분석 실패"

# --- 7. 메인 UI ---
st.title("🩺 한의사 임상 보조 시스템")

if st.session_state.step == "input":
    with st.container():
        st.markdown('<div class="stCard">', unsafe_allow_html=True)
        st.subheader("👤 환자 정보 입력")
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1: name = st.text_input("이름", placeholder="성함")
        with c2: gender = st.selectbox("성별", ["미선택", "남성", "여성"])
        with c3: birth_year = st.text_input("출생년도", placeholder="예: 1985")
        st.divider()
        st.subheader("📝 증상 및 대화 입력")
        raw_text = st.text_area("환자의 주소증을 입력하세요", height=200, label_visibility="collapsed")
        st.markdown('<div class="main-btn">', unsafe_allow_html=True)
        if st.button("✨ 1차 분석 및 문진 확인 시작"):
            if raw_text and birth_year:
                st.session_state.patient_info = {"name": name, "gender": gender, "birth_year": birth_year}
                with st.spinner("분석 중..."):
                    age = calculate_age(birth_year)
                    FIRST_PROMPT = f"환자: {name}({gender}, {age}세)\n대화: {raw_text}\n\n지침: 추가 문진 질문 리스트를 만드세요. 질문 끝에 ? 필수.\n\n[SOAP 요약]: ...\n[추가 확인 사항]: 질문들..."
                    result = analyze_with_hybrid_fallback(FIRST_PROMPT)
                    if "[추가 확인 사항]" in result:
                        parts = result.split("[추가 확인 사항]")
                        st.session_state.soap_result = parts[0].replace("[SOAP 요약]", "").strip()
                        raw_q = re.split(r'\n|(?<=\?)\s*', parts[1].strip())
                        st.session_state.follow_up_questions = [q.strip() for q in raw_q if '?' in q and len(q.strip()) > 5]
                    st.session_state.raw_text = raw_text
                    st.session_state.step = "verify"
                    st.rerun()
        st.markdown('</div></div>', unsafe_allow_html=True)

elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    p = st.session_state.patient_info
    st.write(f"**진료 환자:** {p['name']} ({p['gender']} / {calculate_age(p['birth_year'])}세)")
    for i, q in enumerate(st.session_state.follow_up_questions):
        st.markdown(f'<div class="q-item">{q}</div>', unsafe_allow_html=True)
        st.session_state.additional_responses[f"q_{i}"] = st.text_input(f"답변 {i+1}", key=f"ans_{i}", label_visibility="collapsed")
    st.markdown('<div class="verify-btn">', unsafe_allow_html=True)
    if st.button("✅ 최종 처방 및 치료 계획 생성"):
        responses = "\n".join([f"질문: {q}\n답변: {st.session_state.additional_responses.get(f'q_{i}', '특이사항 없음')}" for i, q in enumerate(st.session_state.follow_up_questions)])
        st.session_state.additional_input = responses
        st.session_state.step = "result"
        st.rerun()
    st.markdown('</div></div>', unsafe_allow_html=True)

elif st.session_state.step == "result":
    if not st.session_state.final_plan:
        with st.spinner("진단 및 KCD 상병 추론 중..."):
            p = st.session_state.patient_info
            age = calculate_age(p['birth_year'])
            FINAL_PROMPT = f"""[치료 DB]: {treatment_db_content}\n[환자]: {p['name']}, {age}세\n[증상]: {st.session_state.raw_text}\n{st.session_state.additional_input}\n\n필수항목:\n1. **[의심되는 질환명]**: KCD 상병코드 및 한방 상병코드(U코드) 포함 추론.\n2. **[차트정리]**: 사실요약 및 안정가료 지도 문구.\n3. **[최종 처방]**: 동측/대측 원리 명시.\n4. **[혈자리 가이드]**: 하단에 이름(코드) [이미지: URL] 형식 작성."""
            st.session_state.final_plan = analyze_with_hybrid_fallback(FINAL_PROMPT)

    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.markdown(f'<div class="model-badge">AI 모델: {st.session_state.current_model}</div>', unsafe_allow_html=True)
    p = st.session_state.patient_info
    st.subheader(f"진료 결과: {p['name']} ({p['gender']} / {calculate_age(p['birth_year'])}세)")
    
    clean_display = re.sub(r'\[이미지:\s*https?:\/\/[^\s\]]+\]', '', st.session_state.final_plan)
    st.markdown(clean_display)
    
    img_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', st.session_state.final_plan, re.I)
    if img_patterns:
        st.divider()
        st.subheader("🖼️ 혈자리 위치 가이드")
        cols = st.columns(2)
        idx = 0
        for name, url in img_patterns:
            with cols[idx % 2]:
                st.image(url.strip(), use_container_width=True)
                st.markdown(f'<div class="acu-caption">{name}</div>', unsafe_allow_html=True)
            idx += 1
    
    # --- 공유 기능 추가 구간 ---
    st.divider()
    st.markdown('<div class="share-btn">', unsafe_allow_html=True)
    if st.button("🔗 공유용 웹페이지 주소 생성"):
        new_id = str(uuid.uuid4())[:8]
        if 'db_storage' not in st.session_state: st.session_state.db_storage = {}
        st.session_state.db_storage[new_id] = {"name": p['name'], "content": st.session_state.final_plan}
        # 생성된 주소 출력
        share_url = f"https://idstring38.streamlit.app/?view={new_id}"
        st.success("주소가 생성되었습니다! (주의: 서버 재시작 시 주소는 만료됩니다)")
        st.code(share_url, language="text")
    st.markdown('</div>', unsafe_allow_html=True)

    if st.button("🔄 다음 환자 진료"):
        clear_form()
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


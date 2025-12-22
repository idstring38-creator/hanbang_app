import streamlit as st
import google.generativeai as genai 
import re
import datetime
import time
import uuid
from groq import Groq
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 설정 및 공유 주소 확인 ---
st.set_page_config(
    page_title="한의사 임상 보조 시스템",
    page_icon="🩺",
    layout="centered"
)

MY_APP_URL = "https://idstring.streamlit.app/" 
query_params = st.query_params
shared_id = query_params.get("view")

# --- 2. 구글 시트 연동 함수 ---
def get_storage_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
    except Exception as e:
        return None

# --- 3. [공유 페이지 모드] ---
if shared_id:
    sheet = get_storage_sheet()
    if sheet:
        try:
            cell = sheet.find(shared_id)
            if cell:
                row_data = sheet.row_values(cell.row)
                patient_name = row_data[2]
                final_content = row_data[4]
                
                st.markdown(f"### 🩺 {patient_name} 진료 결과")
                st.info("🔗 원장님으로부터 공유된 진료 결과 웹페이지입니다.")
                st.markdown('<div style="background-color: white; padding: 25px; border-radius: 16px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">', unsafe_allow_html=True)
                
                clean_display = re.sub(r'\[이미지:\s*https?:\/\/[^\s\]]+\]', '', final_content)
                st.markdown(clean_display)
                
                img_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', final_content, re.I)
                if img_patterns:
                    st.divider()
                    st.subheader("🖼️ 혈자리 위치 가이드")
                    cols = st.columns(2)
                    for idx, (name, url) in enumerate(img_patterns):
                        with cols[idx % 2]:
                            st.image(url.strip(), use_container_width=True)
                            st.markdown(f"<div style='text-align:center; font-weight:700; background:#f1f5f9; padding:5px; border-radius:5px;'>{name}</div>", unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.error("해당 진료 기록을 찾을 수 없습니다.")
        except:
            st.error("데이터 로딩 중 오류 발생")
    
    if st.button("🏠 내 진료실 메인으로 돌아가기"):
        st.query_params.clear()
        st.rerun()
    st.stop()

# --- 4. 초기화 및 세션 관리 ---
if 'patient_info' not in st.session_state:
    st.session_state.patient_info = {"name": "", "gender": "미선택", "birth_year": ""}
if 'step' not in st.session_state:
    st.session_state.step = "input" 
if 'final_plan' not in st.session_state:
    st.session_state.final_plan = ""
if 'shared_link' not in st.session_state:
    st.session_state.shared_link = ""

def calculate_age(birth_year):
    try: return 2025 - int(birth_year) + 1
    except: return "미상"

def clear_form():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- 5. 커스텀 CSS ---
st.markdown("""
    <style>
    .stCard { background-color: #ffffff; border-radius: 16px; padding: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; margin-bottom: 20px; }
    .q-item { background-color: #fefce8; border: 1px solid #fef08a; padding: 12px; border-radius: 10px; color: #854d0e; margin-top: 10px; font-weight: 500; }
    .share-box { background-color: #f8fafc; border: 2px dashed #cbd5e1; padding: 15px; border-radius: 12px; margin-top: 20px; }
    div.stButton > button { border-radius: 15px !important; font-weight: 800 !important; width: 100% !important; }
    .main-btn button { background-color: #2563eb !important; color: white !important; height: 3.5em !important; font-size: 1.2rem !important; }
    .verify-btn button { background-color: #059669 !important; color: white !important; height: 3.5em !important; font-size: 1.2rem !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 6. API 분석 엔진 ---
def analyze_with_hybrid_fallback(prompt):
    api_keys = st.secrets.get("GEMINI_API_KEY", [])
    if isinstance(api_keys, str): api_keys = [api_keys]
    for api_key in api_keys:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
            res = model.generate_content(prompt)
            if res and res.text: return res.text
        except: continue
    return "분석 실패"

# --- 7. 메인 UI ---
st.title("🩺 한방 임상 보조 시스템")

if st.session_state.step == "input":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("👤 환자 정보 입력")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1: name = st.text_input("이름")
    with c2: gender = st.selectbox("성별", ["미선택", "남성", "여성"])
    with c3: birth_year = st.text_input("출생년도")
    raw_text = st.text_area("증상을 입력하세요", height=150)
    
    st.markdown('<div class="main-btn">', unsafe_allow_html=True)
    if st.button("✨ 1차 분석 및 문진 시작"):
        if raw_text:
            st.session_state.patient_info = {"name": name, "gender": gender, "birth_year": birth_year}
            with st.spinner("질문 생성 중..."):
                age = calculate_age(birth_year)
                # 5개 이상 질문 강제 지침 추가
                FIRST_PROMPT = f"""환자: {name}({age}세)\n증상: {raw_text}\n\n[지침]: 최종 진단을 위해 필요한 한의학적 변증 질문을 **반드시 최소 5개 이상** 작성하세요. 질문은 반드시 한 줄에 하나씩 물음표(?)로 끝내야 합니다.\n\n[SOAP 요약]: ...\n[추가 확인 사항]: 질문들..."""
                result = analyze_with_hybrid_fallback(FIRST_PROMPT)
                if "[추가 확인 사항]" in result:
                    parts = result.split("[추가 확인 사항]")
                    st.session_state.soap_result = parts[0].strip()
                    qs = [q.strip() for q in re.split(r'\n|(?<=\?)\s*', parts[1]) if '?' in q]
                    # 만약 AI가 5개 미만으로 주면 강제 보정 로직
                    st.session_state.follow_up_questions = qs if len(qs) >= 5 else (qs + ["그 외에 불편하신 곳이 더 있으신가요?", "증상이 언제부터 시작되었나요?", "평소 소화나 수면은 어떠신가요?", "통증의 양상은 어떠한가요?", "특별히 악화되는 상황이 있나요?"])[:5]
                st.session_state.raw_text = raw_text
                st.session_state.step = "verify"
                st.rerun()
    st.markdown('</div></div>', unsafe_allow_html=True)

elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("🔍 정밀 문진")
    for i, q in enumerate(st.session_state.follow_up_questions):
        st.markdown(f'<div class="q-item">{q}</div>', unsafe_allow_html=True)
        st.session_state.setdefault('responses', {})[f"q_{i}"] = st.text_input(f"답변 {i+1}", key=f"ans_{i}", label_visibility="collapsed")
    
    st.markdown('<div class="verify-btn">', unsafe_allow_html=True)
    if st.button("✅ 최종 처방 생성"):
        st.session_state.step = "result"
        st.rerun()
    st.markdown('</div></div>', unsafe_allow_html=True)

elif st.session_state.step == "result":
    if not st.session_state.final_plan:
        with st.spinner("진단 수립 및 자동 링크 생성 중..."):
            p = st.session_state.patient_info
            age = calculate_age(p['birth_year'])
            ans_str = "\n".join([f"Q: {q} A: {st.session_state.responses.get(f'q_{i}', '')}" for i, q in enumerate(st.session_state.follow_up_questions)])
            
            FINAL_PROMPT = f"[DB]: {st.secrets.get('TREATMENT_DB','')}\n[환자]: {p['name']}({age})\n[증상]: {st.session_state.raw_text}\n{ans_str}\n\n1. [의심되는 질환명] (KCD/U코드 포함)\n2. [차트정리]\n3. [최종 처방]\n4. [혈자리 가이드] 이름(코드) [이미지: URL]"
            st.session_state.final_plan = analyze_with_hybrid_fallback(FINAL_PROMPT)
            
            # --- 링크 자동 생성 로직 ---
            new_id = str(uuid.uuid4())[:8]
            sheet = get_storage_sheet()
            if sheet:
                try:
                    sheet.append_row([new_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), f"{p['name']}({age})", "AutoGenerated", st.session_state.final_plan])
                    st.session_state.shared_link = f"{MY_APP_URL}?view={new_id}"
                except: pass

    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader(f"진료 결과: {st.session_state.patient_info['name']}")
    
    # 결과 출력
    clean_display = re.sub(r'\[이미지:\s*https?:\/\/[^\s\]]+\]', '', st.session_state.final_plan)
    st.markdown(clean_display)
    
    # 이미지 가이드
    img_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', st.session_state.final_plan, re.I)
    if img_patterns:
        st.divider()
        cols = st.columns(2)
        for idx, (name, url) in enumerate(img_patterns):
            with cols[idx % 2]:
                st.image(url.strip(), use_container_width=True)
                st.markdown(f"<div style='text-align:center; font-weight:bold;'>{name}</div>", unsafe_allow_html=True)

    # --- 자동 생성된 링크 상시 표시 ---
    if st.session_state.shared_link:
        st.markdown('<div class="share-box">', unsafe_allow_html=True)
        st.markdown("**🌐 환자 공유용 영구 웹페이지 주소**")
        st.code(st.session_state.shared_link, language="text")
        st.caption("위 주소를 복사하여 환자분께 문자로 보내주세요.")
        st.markdown('</div>', unsafe_allow_html=True)

    if st.button("🔄 다음 환자 진료"):
        clear_form()
    st.markdown('</div>', unsafe_allow_html=True)

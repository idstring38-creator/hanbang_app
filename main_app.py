import streamlit as st
import google.generativeai as genai 
import re
import datetime
import time
from groq import Groq
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 설정 및 초기화 ---
st.set_page_config(
    page_title="한의사 임상 보조 시스템",
    page_icon="🩺",
    layout="centered"
)

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

def calculate_age(birth_year):
    try:
        current_year = 2025 # 현재 시스템 기준 연도
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

# --- 2. 구글 시트 저장 ---
def save_to_google_sheets(content):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
        now = datetime.datetime.now()
        p = st.session_state.patient_info
        age = calculate_age(p['birth_year'])
        patient_str = f"{p['name']}({p['gender']}/{age}세)"
        row = [now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), patient_str, st.session_state.soap_result[:100], content]
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"시트 저장 실패: {e}")
        return False

# --- 3. 커스텀 CSS ---
st.markdown("""
    <style>
    .stCard { background-color: #ffffff; border-radius: 16px; padding: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; margin-bottom: 20px; }
    .q-item { background-color: #fefce8; border: 1px solid #fef08a; padding: 12px; border-radius: 10px; color: #854d0e; margin-top: 10px; font-weight: 500; }
    .acu-caption { font-size: 1.1rem !important; font-weight: 700 !important; color: #0f172a !important; text-align: center; margin-top: 5px; background: #f1f5f9; padding: 5px; border-radius: 5px; }
    .stButton>button { border-radius: 12px; height: 3em; font-weight: 700; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. API 설정 ---
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
                    if res and res.text: return res.text
                except: continue
        except: continue
    if groq_client:
        try:
            res = groq_client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.3-70b-versatile", temperature=0.2)
            return res.choices[0].message.content
        except: pass
    return "분석 실패"

# --- 5. UI 로직 ---
st.title("🩺 한방 임상 보조 시스템")

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
        
        if st.button("✨ 1차 분석 및 문진 확인"):
            if raw_text and birth_year:
                st.session_state.patient_info = {"name": name, "gender": gender, "birth_year": birth_year}
                with st.spinner("분석 중..."):
                    age = calculate_age(birth_year)
                    FIRST_PROMPT = f"""환자: {name}({gender}, {age}세)\n대화: {raw_text}\n\n지침: 위 내용을 바탕으로 추가 문진이 필요한 항목을 질문 리스트로 만드세요. 질문은 한 줄에 하나씩 물음표(?)로 끝내야 합니다.\n\n[SOAP 요약]: ...\n[추가 확인 사항]: 질문들..."""
                    result = analyze_with_hybrid_fallback(FIRST_PROMPT)
                    if "[추가 확인 사항]" in result:
                        parts = result.split("[추가 확인 사항]")
                        st.session_state.soap_result = parts[0].replace("[SOAP 요약]", "").strip()
                        raw_q = re.split(r'\n|(?<=\?)\s*', parts[1].strip())
                        st.session_state.follow_up_questions = [q.strip() for q in raw_q if '?' in q and len(q.strip()) > 5]
                    st.session_state.raw_text = raw_text
                    st.session_state.step = "verify"
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    p = st.session_state.patient_info
    st.write(f"**환자:** {p['name']} ({p['gender']} / {calculate_age(p['birth_year'])}세)")
    st.subheader("🔍 추가 문진")
    
    for i, q in enumerate(st.session_state.follow_up_questions):
        st.markdown(f'<div class="q-item">{q}</div>', unsafe_allow_html=True)
        st.session_state.additional_responses[f"q_{i}"] = st.text_input(f"답변 {i+1}", key=f"ans_{i}", label_visibility="collapsed")

    if st.button("✅ 최종 처방 생성"):
        responses = "\n".join([f"질문: {q}\n답변: {st.session_state.additional_responses.get(f'q_{i}', '특이사항 없음')}" for i, q in enumerate(st.session_state.follow_up_questions)])
        st.session_state.additional_input = responses
        st.session_state.step = "result"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.step == "result":
    if not st.session_state.final_plan:
        with st.spinner("최종 치료 계획 수립 중..."):
            p = st.session_state.patient_info
            age = calculate_age(p['birth_year'])
            FINAL_PROMPT = f"""
            [치료 DB]: {treatment_db_content}
            [환자 기초정보]: {p['name']}, {p['gender']}, {age}세
            [증상 및 추가답변]: {st.session_state.raw_text}\n{st.session_state.additional_input}

            당신은 한의사 보조 AI입니다. 아래 형식을 엄격히 지켜 답변하세요.

            1. **[의심되는 질환명]**: 양방/한방 병명을 모두 제시하고, 환자의 증상과 대조하여 추론 과정을 아주 상세히 서술하세요.
            2. **[차트정리]**: 환자의 진술과 답변을 사실에 기반해 요약하고, 마지막에 '환자에게 안정가료를 지도하고 무리한 동작을 삼갈 것을 권고함. 증상 악화 시 즉시 내원하도록 지도함' 문구를 포함하세요. 절대 가상 내용을 추가하지 마세요.
            3. **[최종 처방 및 치료 계획]**: 치료 DB의 원칙을 적용하세요. 특히 '동측(환측) 취혈'인지 '대측(건측) 취혈'인지 원리와 응용법을 명확히 명시하세요.
            4. 추천 혈자리는 '이름(코드)' 형식으로만 본문에 작성하세요.
            5. **주의**: 답변 가장 하단에 이미지 생성을 위한 `이름(코드) [이미지: URL]` 리스트만 한 줄씩 나열하세요. (예전 코드 방식 엄수)
            """
            st.session_state.final_plan = analyze_with_hybrid_fallback(FINAL_PROMPT)

    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    p = st.session_state.patient_info
    st.write(f"**진료 결과:** {p['name']} ({p['gender']} / {calculate_age(p['birth_year'])}세)")
    
    # 본문 출력 (이미지 태그 제거 후)
    clean_display = re.sub(r'\[이미지:\s*https?:\/\/[^\s\]]+\]', '', st.session_state.final_plan)
    st.markdown(clean_display)
    
    # 예전 코드의 이미지 추출 로직 적용
    img_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', st.session_state.final_plan, re.I)
    if img_patterns:
        st.divider()
        st.subheader("🖼️ 혈자리 위치 가이드")
        seen_urls = set()
        cols = st.columns(2)
        idx = 0
        for name, url in img_patterns:
            clean_url = url.strip()
            if clean_url not in seen_urls:
                with cols[idx % 2]:
                    st.image(clean_url, use_container_width=True)
                    st.markdown(f'<div class="acu-caption">{name}</div>', unsafe_allow_html=True)
                seen_urls.add(clean_url)
                idx += 1
    
    if st.button("📲 모바일 전송"):
        if save_to_google_sheets(st.session_state.final_plan): st.success("전송 완료!")
    if st.button("🔄 다음 환자"):
        clear_form()
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

with st.sidebar:
    if st.button("🏠 초기화"):
        clear_form()
        st.rerun()

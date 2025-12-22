import streamlit as st
import google.generativeai as genai 
import re
import datetime
import uuid
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 설정 및 주소 ---
st.set_page_config(page_title="한의사 임상 보조 시스템", page_icon="🩺", layout="centered")
MY_APP_URL = "https://idstring.streamlit.app/" 
query_params = st.query_params
shared_id = query_params.get("view")

# --- 2. 구글 시트 연동 ---
def get_storage_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
    except: return None

# --- 3. [공유 모드] ---
if shared_id:
    sheet = get_storage_sheet()
    if sheet:
        try:
            cell = sheet.find(shared_id)
            if cell:
                row_data = sheet.row_values(cell.row)
                st.markdown(f"### 🩺 {row_data[2]} 진료 결과")
                st.markdown('<div style="background-color: white; padding: 25px; border-radius: 16px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">', unsafe_allow_html=True)
                st.markdown(row_data[4], unsafe_allow_html=True) # HTML 스타일 포함 출력
                st.markdown('</div>', unsafe_allow_html=True)
        except: st.error("기록 로딩 실패")
    if st.button("🏠 메인으로"):
        st.query_params.clear()
        st.rerun()
    st.stop()

# --- 4. 초기화 ---
for key in ['patient_info', 'step', 'final_plan', 'shared_link', 'responses']:
    if key not in st.session_state:
        if key == 'patient_info': st.session_state[key] = {"name": "", "gender": "미선택", "birth_year": ""}
        elif key == 'step': st.session_state[key] = "input"
        else: st.session_state[key] = ""

def calculate_age(birth_year):
    try: return 2025 - int(birth_year) + 1
    except: return "미상"

# --- 5. 커스텀 CSS (제목 스타일 강화) ---
st.markdown("""
    <style>
    .stCard { background-color: #ffffff; border-radius: 16px; padding: 25px; border: 1px solid #e2e8f0; margin-bottom: 20px; }
    .result-title { 
        color: #1e40af; 
        font-size: 1.4rem; 
        font-weight: 800; 
        border-left: 5px solid #1e40af; 
        padding-left: 12px; 
        margin-top: 25px; 
        margin-bottom: 10px; 
    }
    .q-item { background-color: #fefce8; padding: 12px; border-radius: 10px; color: #854d0e; margin-top: 10px; font-weight: 500; }
    .share-box { background-color: #f8fafc; border: 2px dashed #cbd5e1; padding: 15px; border-radius: 12px; margin-top: 20px; }
    div.stButton > button { border-radius: 12px !important; font-weight: 800 !important; width: 100% !important; }
    .main-btn button { background-color: #2563eb !important; color: white !important; height: 3.5em !important; }
    .verify-btn button { background-color: #059669 !important; color: white !important; height: 3.5em !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 6. UI 로직 ---
st.title("🩺 한방 임상 보조 시스템")

if st.session_state.step == "input":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("👤 환자 정보 입력")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1: name = st.text_input("이름")
    with c2: gender = st.selectbox("성별", ["미선택", "남성", "여성"])
    with c3: birth_year = st.text_input("출생년도")
    raw_text = st.text_area("증상을 입력하세요", height=150)
    
    if st.button("✨ 1차 분석 및 문진 시작"):
        if raw_text:
            st.session_state.patient_info = {"name": name, "gender": gender, "birth_year": birth_year}
            with st.spinner("질문 생성 중..."):
                age = calculate_age(birth_year)
                FIRST_PROMPT = f"""환자: {name}({age}세)\n증상: {raw_text}\n\n[지침]: 정확한 변증을 위해 질문 5개 이상 필수 생성. 질문마다 ? 포함.\n[SOAP 요약]: ...\n[추가 확인 사항]: 질문들..."""
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"][0])
                model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
                result = model.generate_content(FIRST_PROMPT).text
                if "[추가 확인 사항]" in result:
                    parts = result.split("[추가 확인 사항]")
                    qs = [q.strip() for q in re.split(r'\n|(?<=\?)\s*', parts[1]) if '?' in q]
                    st.session_state.follow_up_questions = (qs + ["불편하신 곳이 더 있나요?", "언제부터 시작되었나요?", "평소 소화는 어떠세요?"])[:5]
                st.session_state.raw_text = raw_text
                st.session_state.step = "verify"
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("🔍 정밀 문진")
    if not isinstance(st.session_state.responses, dict): st.session_state.responses = {}
    for i, q in enumerate(st.session_state.follow_up_questions):
        st.markdown(f'<div class="q-item">{q}</div>', unsafe_allow_html=True)
        st.session_state.responses[f"q_{i}"] = st.text_input(f"답변 {i+1}", key=f"ans_{i}", label_visibility="collapsed")
    if st.button("✅ 최종 처방 생성"):
        st.session_state.step = "result"
        st.rerun()

elif st.session_state.step == "result":
    if not st.session_state.final_plan:
        with st.spinner("진단 수립 및 자동 링크 생성 중..."):
            p = st.session_state.patient_info
            age = calculate_age(p['birth_year'])
            ans_str = "\n".join([f"Q: {q} A: {st.session_state.responses.get(f'q_{i}', '')}" for i, q in enumerate(st.session_state.follow_up_questions)])
            db = st.secrets.get("TREATMENT_DB", "")
            
            FINAL_PROMPT = f"""
            [TREATMENT_DB]: {db}
            [환자]: {p['name']}({age}) / [주소증]: {st.session_state.raw_text}\n{ans_str}

            [작성 지침 - 엄격히 준수]:
            1. 모든 항목의 제목은 <div class='result-title'>항목명</div> 태그로 감쌀 것.
            2. **[의심되는 질환명]**: 반드시 양방병명(KCD 코드 포함)과 한방병명을 나란히 병기할 것.
            3. **[차트 정리]**: 진료기록부 기록 원칙(정확성, 상세함, 일관성)을 준수. 주소증, 진단, 치료내용(일반적 침, 뜸, 부항 치료 시행함)을 과장 없이 상세히 기록할 것.
            4. **[치료 혈자리]**: 
               - 오직 [TREATMENT_DB]에 기재된 혈자리만을 출력할 것. DB에 없는 처방은 절대 금지.
               - DB에 명시된 '대측 취혈' 또는 '동측 취혈' 원리를 무조건 텍스트로 포함하여 기재할 것.
            5. **[혈자리 가이드]**: 하단에 '이름(코드) [이미지: URL]' 형식으로 마무리.
            """
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"][0])
            model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
            st.session_state.final_plan = model.generate_content(FINAL_PROMPT).text
            
            # 링크 자동 생성
            new_id = str(uuid.uuid4())[:8]
            sheet = get_storage_sheet()
            if sheet:
                try:
                    sheet.append_row([new_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), f"{p['name']}({age})", "Auto", st.session_state.final_plan])
                    st.session_state.shared_link = f"{MY_APP_URL}?view={new_id}"
                except: pass

    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader(f"진료 결과: {st.session_state.patient_info['name']}")
    
    # 이미지 가이드 분리 및 본문 출력
    main_text = re.sub(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', '', st.session_state.final_plan)
    st.markdown(main_text, unsafe_allow_html=True)
    
    # 혈자리 이미지 출력
    img_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', st.session_state.final_plan, re.I)
    if img_patterns:
        st.divider()
        cols = st.columns(2)
        for idx, (name, url) in enumerate(img_patterns):
            with cols[idx % 2]:
                st.image(url.strip(), use_container_width=True)
                st.markdown(f"<div style='text-align:center; font-weight:bold;'>{name}</div>", unsafe_allow_html=True)

    if st.session_state.shared_link:
        st.markdown('<div class="share-box">', unsafe_allow_html=True)
        st.markdown("**🌐 환자 공유용 웹페이지 주소**")
        st.code(st.session_state.shared_link, language="text")
        st.markdown('</div>', unsafe_allow_html=True)

    if st.button("🔄 다음 환자 진료"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

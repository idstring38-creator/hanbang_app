import streamlit as st
import google.generativeai as genai 
import re
import datetime
import uuid
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 설정 및 세션 초기화 ---
st.set_page_config(page_title="한방 임상 보조 시스템", page_icon="🩺", layout="centered")

for key in ['step', 'patient_info', 'follow_up_questions', 'responses', 'final_plan', 'shared_link', 'raw_text']:
    if key not in st.session_state:
        if key == 'step': st.session_state[key] = "input"
        elif key == 'patient_info': st.session_state[key] = {"name": "", "gender": "미선택", "birth_year": ""}
        elif key in ['follow_up_questions', 'responses']: st.session_state[key] = [] if key=='follow_up_questions' else {}
        else: st.session_state[key] = ""

MY_APP_URL = "https://idstring.streamlit.app/" 

# --- 2. 구글 시트 연동 ---
def get_storage_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
    except: return None

# --- 3. [공유 모드 확인] ---
query_params = st.query_params
shared_id = query_params.get("view")

if shared_id:
    sheet = get_storage_sheet()
    if sheet:
        try:
            cell = sheet.find(shared_id)
            if cell:
                row_data = sheet.row_values(cell.row)
                st.markdown(f"### 🩺 {row_data[2]} 최종진단")
                st.markdown('<div style="background-color: white; padding: 25px; border-radius: 16px; border: 1px solid #e2e8f0;">', unsafe_allow_html=True)
                display_html = row_data[4].replace("```html", "").replace("```", "")
                st.markdown(display_html, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        except: st.error("기록을 찾을 수 없습니다.")
    if st.button("🏠 메인으로"):
        st.query_params.clear()
        st.rerun()
    st.stop()

# --- 4. 커스텀 CSS (강조된 제목 및 여백) ---
st.markdown("""
    <style>
    .stCard { background-color: #ffffff; border-radius: 16px; padding: 25px; border: 1px solid #e2e8f0; margin-bottom: 20px; }
    
    /* 항목 제목 스타일: 더 크고, 두껍고, 선명한 파란색 */
    .result-title { 
        color: #0056b3 !important; 
        font-size: 1.8rem !important; 
        font-weight: 900 !important; 
        border-left: 8px solid #0056b3; 
        padding-left: 15px;
        margin-top: 50px !important; /* 항목 간 충분한 여백 */
        margin-bottom: 20px !important;
        background-color: #f0f7ff;
        padding-top: 10px;
        padding-bottom: 10px;
        border-radius: 4px;
    }
    
    div.stButton > button {
        background-color: #1d4ed8 !important; color: white !important;
        font-size: 1.3rem !important; font-weight: 800 !important;
        height: 4em !important; width: 100% !important;
        border-radius: 15px !important; border: none !important;
        box-shadow: 0 4px 15px rgba(29, 78, 216, 0.3) !important;
    }
    
    .q-item { background-color: #f8fafc; padding: 15px; border-radius: 10px; border-left: 5px solid #3b82f6; margin-top: 10px; font-weight: 600; }
    
    /* 섹션 간 줄바꿈 효과 */
    .section-gap { margin-bottom: 40px; }
    </style>
    """, unsafe_allow_html=True)

def calculate_age(birth_year):
    try: return 2025 - int(birth_year) + 1
    except: return "미상"

# --- 5. UI 로직 ---

if st.session_state.step == "input":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("👤 환자 정보 및 증상 입력")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1: name = st.text_input("이름", placeholder="성함")
    with c2: gender = st.selectbox("성별", ["남성", "여성", "미선택"])
    with c3: birth_year = st.text_input("출생년도", placeholder="예: 1985")
    raw_text = st.text_area("주소증 입력", height=150)
    
    if st.button("✨ 분석 시작 및 문진 생성"):
        if raw_text:
            st.session_state.patient_info = {"name": name, "gender": gender, "birth_year": birth_year}
            with st.spinner("AI가 분석 중입니다..."):
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"][0])
                model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
                PROMPT = f"환자: {name}, 증상: {raw_text}\n[지침]: 변증을 위해 질문 5개 이상 필수 생성. ?로 끝나는 질문 리스트.\n[추가 확인 사항]: 질문들..."
                try:
                    res = model.generate_content(PROMPT).text
                    qs = [q.strip() for q in re.split(r'\n|(?<=\?)\s*', res.split("[추가 확인 사항]")[-1]) if '?' in q]
                    defaults = ["증상 발생 시기?", "통증 양상?", "소화/배변?", "수면/컨디션?", "악화 조건?"]
                    st.session_state.follow_up_questions = (qs + defaults)[:max(5, len(qs))]
                    st.session_state.raw_text = raw_text
                    st.session_state.step = "verify"
                    st.rerun()
                except: st.error("API 연결 실패")
    st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("🔍 정밀 문진")
    for i, q in enumerate(st.session_state.follow_up_questions):
        st.markdown(f'<div class="q-item">{i+1}. {q}</div>', unsafe_allow_html=True)
        st.session_state.responses[f"q_{i}"] = st.text_input(f"답변 {i+1}", key=f"ans_{i}")
    
    if st.button("✅ 심층 진단 생성"):
        st.session_state.step = "result"
        st.rerun()

elif st.session_state.step == "result":
    if not st.session_state.final_plan:
        with st.spinner("최종 진단 리포트를 작성 중입니다..."):
            p = st.session_state.patient_info
            age = calculate_age(p['birth_year'])
            ans_str = "\n".join([f"Q: {q} A: {st.session_state.responses.get(f'q_{i}', '')}" for i, q in enumerate(st.session_state.follow_up_questions)])
            db_content = st.secrets.get("TREATMENT_DB", "")
            
            FINAL_PROMPT = f"""
            [TREATMENT_DB]: {db_content}
            환자: {p['name']}({p['gender']}, {age}세) / 증상: {st.session_state.raw_text} / 답변: {ans_str}

            [지침]:
            1. 모든 대제목은 <div class='result-title'>제목명</div>을 사용하며, 제목 뒤에 <div class='section-gap'></div>를 추가해라.
            2. **[환자 정보 요약]**, **[차트 정리]**, **[변증 및 진단]**, **[혈자리 처방]**, **[추가 혈자리 권유]**, **[혈자리 가이드]** 순서로 작성.
            3. [차트 정리]에 법적 방어 문구 필수 포함.
            4. [변증 및 진단]은 500자 이상 심층 기술, U코드 사용.
            5. [혈자리 처방]은 DB 근거, 혈자리마다 <br> 줄바꿈.
            6. [혈자리 가이드] 형식: "(동측/대측) 혈자리이름 [이미지: URL]" (이미지 URL은 대괄호 안에 정확히 기재)
            """
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"][0])
            model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
            st.session_state.final_plan = model.generate_content(FINAL_PROMPT).text
            
            new_id = str(uuid.uuid4())[:8]
            sheet = get_storage_sheet()
            if sheet:
                sheet.append_row([new_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), f"{p['name']}", "자동", st.session_state.final_plan])
                st.session_state.shared_link = f"{MY_APP_URL}?view={new_id}"

    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader(f"📋 {st.session_state.patient_info['name']} 최종진단")
    
    # --- 출력 로직 보완 ---
    raw_plan = st.session_state.final_plan.replace("```html", "").replace("```", "")
    
    # 1. 혈자리 가이드 분리
    parts = raw_plan.split("<div class='result-title'>혈자리 가이드</div>")
    main_content = parts[0]
    st.markdown(main_content, unsafe_allow_html=True)

    if len(parts) > 1:
        st.markdown("<div class='result-title'>혈자리 가이드</div>", unsafe_allow_html=True)
        guide_text = parts[1]
        
        # 2. 이미지 URL 추출 및 텍스트 정제 (정규표현식 강화)
        img_patterns = re.findall(r'(\((?:동측|대측)\)\s*[가-힣0-9a-zA-Z\s]+)\s*\[이미지:\s*(https?://[^\s\]]+)\]', guide_text)
        
        # 이미지 태그를 제거한 순수 텍스트 먼저 출력
        clean_text = re.sub(r'\[이미지:\s*https?://[^\s\]]+\]', '', guide_text)
        st.markdown(clean_text, unsafe_allow_html=True)
        
        # 3. 추출된 이미지 실제 렌더링
        if img_patterns:
            st.write("---")
            cols = st.columns(2)
            for idx, (label, url) in enumerate(img_patterns):
                with cols[idx % 2]:
                    st.image(url.strip(), use_container_width=True)
                    st.markdown(f"<div style='text-align:center; font-weight:bold; color:#0056b3;'>{label}</div>", unsafe_allow_html=True)

    # 4. 환자 공유 주소 및 복사 버튼
    if st.session_state.shared_link:
        st.divider()
        st.markdown("### 🔗 환자용 공유 주소")
        col_link, col_copy = st.columns([4, 1])
        with col_link:
            st.text_input("공유 링크", st.session_state.shared_link, label_visibility="collapsed")
        with col_copy:
            # st.code는 내장 복사 버튼을 제공하므로 가장 효율적
            st.code(st.session_state.shared_link, language=None)
            st.caption("위 박스 우측 버튼을 클릭하여 복사")

    if st.button("🔄 다음 환자 진료 시작"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

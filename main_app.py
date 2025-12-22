import streamlit as st
import google.generativeai as genai 
import re
import datetime
import uuid
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 설정 및 세션 초기화 ---
st.set_page_config(page_title="한방 임상 보조 시스템", page_icon="🩺", layout="centered")

# 세션 상태 강제 초기화 (AttributeError 방지)
keys = ['step', 'patient_info', 'follow_up_questions', 'responses', 'final_plan', 'shared_link', 'raw_text']
for key in keys:
    if key not in st.session_state:
        if key == 'step': st.session_state[key] = "input"
        elif key in ['follow_up_questions', 'responses']: st.session_state[key] = [] if key=='follow_up_questions' else {}
        elif key == 'patient_info': st.session_state[key] = {"name": "", "gender": "미선택", "birth_year": ""}
        else: st.session_state[key] = ""

# 깃허브 이미지 기본 경로 설정 (원장님 깃허브 정보 반영)
GITHUB_RAW_URL = "https://raw.githubusercontent.com/idstring38-creator/hanbang_app/main/images/"
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
                # HTML 태그 렌더링 보완
                content = row_data[4].replace("```html", "").replace("```", "")
                st.markdown(content, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        except: st.error("해당 진료 기록을 찾을 수 없거나 만료되었습니다.")
    if st.button("🏠 내 진료실 메인으로 이동"):
        st.query_params.clear()
        st.rerun()
    st.stop()

# --- 4. 커스텀 CSS (제목 가독성 및 여백) ---
st.markdown(f"""
    <style>
    .stCard {{ background-color: #ffffff; border-radius: 16px; padding: 25px; border: 1px solid #e2e8f0; margin-bottom: 20px; }}
    .result-title {{ 
        color: #0056b3 !important; font-size: 1.8rem !important; font-weight: 900 !important; 
        border-left: 8px solid #0056b3; padding: 10px 15px; margin-top: 50px !important; margin-bottom: 25px !important;
        background-color: #f0f7ff; border-radius: 4px;
    }}
    div.stButton > button {{
        background-color: #1d4ed8 !important; color: white !important;
        font-size: 1.3rem !important; font-weight: 800 !important;
        height: 3.5em !important; width: 100% !important; border-radius: 12px !important;
    }}
    .q-item {{ background-color: #f8fafc; padding: 15px; border-radius: 10px; border-left: 5px solid #3b82f6; margin-top: 10px; font-weight: 600; }}
    </style>
    """, unsafe_allow_html=True)

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
                PROMPT = f"환자: {name}, 증상: {raw_text}\n질문 5개 이상 생성. ?로 끝날 것."
                res = model.generate_content(PROMPT).text
                qs = [q.strip() for q in re.split(r'\n|(?<=\?)\s*', res) if '?' in q]
                st.session_state.follow_up_questions = qs[:7]
                st.session_state.raw_text = raw_text
                st.session_state.step = "verify"
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("🔍 정밀 문진")
    for i, q in enumerate(st.session_state.follow_up_questions):
        st.markdown(f'<div class="q-item">{i+1}. {q}</div>', unsafe_allow_html=True)
        st.session_state.responses[f"q_{i}"] = st.text_input(f"답변 {i+1}", key=f"ans_{i}")
    
    if st.button("✅ 최종 진단 결과 보기"):
        st.session_state.step = "result"
        st.rerun()

elif st.session_state.step == "result":
    if not st.session_state.final_plan:
        with st.spinner("최종 리포트 생성 중..."):
            p = st.session_state.patient_info
            ans_str = "\n".join([f"Q: {q} A: {st.session_state.responses.get(f'q_{i}', '')}" for i, q in enumerate(st.session_state.follow_up_questions)])
            db_content = st.secrets.get("TREATMENT_DB", "")
            
            FINAL_PROMPT = f"""
            [환자]: {p['name']}, [주소증]: {st.session_state.raw_text}, [답변]: {ans_str}
            [TREATMENT_DB]: {db_content}
            
            지침:
            1. 대제목은 <div class='result-title'>제목</div> 형식을 사용하고 항목간 한 줄씩 띄울 것.
            2. [혈자리 가이드] 섹션에서 각 혈자리는 "(동측/대측) 혈자리명(코드)" 형식으로 작성하고, 
               그 바로 뒤에 [IMG:코드] 태그를 붙일 것. (예: (동측) 합곡(LI4) [IMG:LI4])
            3. 모든 한의학 상병명은 U코드를 병기할 것.
            4. 변증은 500자 이상 상세히 작성할 것.
            """
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"][0])
            model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
            st.session_state.final_plan = model.generate_content(FINAL_PROMPT).text
            
            new_id = str(uuid.uuid4())[:8]
            sheet = get_storage_sheet()
            if sheet:
                sheet.append_row([new_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), p['name'], "자동", st.session_state.final_plan])
                st.session_state.shared_link = f"{MY_APP_URL}?view={new_id}"

    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader(f"📋 {st.session_state.patient_info['name']} 환자 최종진단")
    
    # 텍스트 정제 및 HTML 출력
    raw_plan = st.session_state.final_plan.replace("```html", "").replace("```", "")
    
    # 섹션별 분리 출력 (이미지 처리를 위해)
    if "<div class='result-title'>혈자리 가이드</div>" in raw_plan:
        main_part, guide_part = raw_plan.split("<div class='result-title'>혈자리 가이드</div>")
        st.markdown(main_part, unsafe_allow_html=True)
        st.markdown("<div class='result-title'>혈자리 가이드</div>", unsafe_allow_html=True)
        
        # 혈자리 가이드 텍스트에서 이미지 태그 추출 및 실제 이미지 출력
        lines = guide_part.split('\n')
        for line in lines:
            if line.strip():
                st.markdown(re.sub(r'\[IMG:.*?\]', '', line), unsafe_allow_html=True)
                img_match = re.search(r'\[IMG:(.*?)\]', line)
                if img_match:
                    code = img_match.group(1).strip()
                    img_url = f"{GITHUB_RAW_URL}{code}.jpg"
                    st.image(img_url, width=300, caption=f"{code} 위치 가이드")
    else:
        st.markdown(raw_plan, unsafe_allow_html=True)

    # 🔗 복사 기능 구현 (st.code 활용)
    if st.session_state.shared_link:
        st.write("---")
        st.markdown("### 🔗 환자용 공유 주소 (아래 박스 우측 버튼을 눌러 복사)")
        st.code(st.session_state.shared_link, language="bash") # st.code는 기본적으로 복사 버튼을 제공함
        st.caption("복사한 링크를 카카오톡이나 문자로 환자분께 전송해 주세요.")

    if st.button("🔄 다음 환자 진료 시작"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

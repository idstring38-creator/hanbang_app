import streamlit as st
import google.generativeai as genai 
import re
import datetime
import uuid
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 설정 및 세션 초기화 ---
st.set_page_config(page_title="한방 임상 보조 시스템", page_icon="🩺", layout="centered")

for key in ['step', 'patient_info', 'follow_up_questions', 'responses', 'final_plan', 'shared_link']:
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

# --- 4. 커스텀 CSS (파란색 큰 제목 및 큰 버튼) ---
st.markdown("""
    <style>
    .stCard { background-color: #ffffff; border-radius: 16px; padding: 25px; border: 1px solid #e2e8f0; margin-bottom: 20px; }
    .result-title { 
        color: #1d4ed8 !important; font-size: 1.6rem !important; font-weight: 800 !important; 
        border-bottom: 3px solid #1d4ed8; padding-bottom: 8px; margin-top: 35px; margin-bottom: 15px; 
    }
    div.stButton > button {
        background-color: #1d4ed8 !important; color: white !important;
        font-size: 1.3rem !important; font-weight: 800 !important;
        height: 4em !important; width: 100% !important;
        border-radius: 15px !important; border: none !important;
        box-shadow: 0 4px 15px rgba(29, 78, 216, 0.3) !important;
    }
    div.stButton > button:hover { background-color: #1e40af !important; }
    .q-item { background-color: #f8fafc; padding: 15px; border-radius: 10px; border-left: 5px solid #3b82f6; margin-top: 10px; font-weight: 600; }
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
    
    if st.button("✨ 분석 시작 및 문진 생성 (최소 5개)"):
        if raw_text:
            st.session_state.patient_info = {"name": name, "gender": gender, "birth_year": birth_year}
            with st.spinner("질문을 생성 중입니다..."):
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"][0])
                model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
                PROMPT = f"환자: {name}, 증상: {raw_text}\n[지침]: 변증을 위해 질문 5개 이상 필수 생성. 한 줄에 하나씩 ?로 끝낼 것.\n[추가 확인 사항]: 질문들..."
                try:
                    res = model.generate_content(PROMPT).text
                    qs = [q.strip() for q in re.split(r'\n|(?<=\?)\s*', res.split("[추가 확인 사항]")[-1]) if '?' in q]
                    defaults = ["증상 발생 시기는?", "통증 양상은?", "소화 상태는?", "수면 상태는?", "악화 요인은?"]
                    st.session_state.follow_up_questions = (qs + defaults)[:max(5, len(qs))]
                    st.session_state.raw_text = raw_text
                    st.session_state.step = "verify"
                    st.rerun()
                except: st.error("API 연결 오류")
    st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("🔍 정밀 문진")
    questions = st.session_state.get('follow_up_questions', [])
    for i, q in enumerate(questions):
        st.markdown(f'<div class="q-item">{i+1}. {q}</div>', unsafe_allow_html=True)
        st.session_state.responses[f"q_{i}"] = st.text_input(f"답변 {i+1}", key=f"ans_{i}")
    
    if st.button("✅ 최종 처방 생성 및 저장"):
        st.session_state.step = "result"
        st.rerun()

elif st.session_state.step == "result":
    if not st.session_state.final_plan:
        with st.spinner("종합 진단 및 리포트 구성 중..."):
            p = st.session_state.patient_info
            age = calculate_age(p['birth_year'])
            ans_str = "\n".join([f"Q: {q} A: {st.session_state.responses.get(f'q_{i}', '')}" for i, q in enumerate(st.session_state.follow_up_questions)])
            db = st.secrets.get("TREATMENT_DB", "")
            
            FINAL_PROMPT = f"""
            [TREATMENT_DB]: {db}
            환자: {p['name']}({age}세), 주소증: {st.session_state.raw_text}, 문진답변: {ans_str}
            
            [지침 - 아래 순서 및 형식을 엄격히 준수]:
            1. 모든 대제목은 <div class='result-title'>제목명</div> 형식을 사용할 것.
            2. **[환자 정보 요약]**: 성별, 연령, 주요 호소 증상을 간략히 정리.
            3. **[차트 정리]**: (순서 중요) 환자 정보 요약 다음에 위치. 
               - 의료법 준수 원칙(정확성, 상세함, 일관성)에 의거하여 기록.
               - 반드시 포함할 문구: "시술 전후 환처 및 수술 부위를 철저히 소독하였음", "시술 후 발생 가능한 부작용(멍, 통증 등)에 대해 상세히 설명함", "진료 후 무리한 활동을 피하고 충분한 안정을 취할 것을 지도함(안정가료 지시)".
               - 하단 '변증 및 진단'에서 판단한 응급 상황 여부를 간략히 언급할 것 (예: "현재 응급 처치가 필요한 red flag 사인은 관찰되지 않음").
            4. **[변증 및 진단]**: 
               - 양방상병명(KCD 코드 포함)과 한방상병명을 병기할 것.
               - **[응급 판단]**: 현재 증상이 뇌혈관질환, 심혈관질환, 급성 복증 등 응급실 전원이 필요한 상황인지 판단하여 기재.
            5. **[혈자리 처방]**: 
               - 형식: "(동측/대측) (혈자리 이름) : 해당 혈자리를 선정한 자세한 한의학적/해부학적 이유"
               - 반드시 [TREATMENT_DB]에 근거할 것.
            6. **[혈자리 가이드]**: '혈자리 이름 [이미지: URL]' 형식으로 작성.
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
    
    # 텍스트 전처리 (이미지 태그 분리 및 HTML 정제)
    clean_html = st.session_state.final_plan.replace("```html", "").replace("```", "")
    
    # 이미지 가이드를 제외한 본문 출력
    content_parts = clean_html.split("<div class='result-title'>혈자리 가이드</div>")
    main_body = content_parts[0]
    st.markdown(main_body, unsafe_allow_html=True)

    # 혈자리 가이드 및 이미지 출력 (가이드 제목 바로 다음에 이미지 출력)
    if len(content_parts) > 1:
        st.markdown("<div class='result-title'>혈자리 가이드</div>", unsafe_allow_html=True)
        guide_text = content_parts[1]
        
        # 이미지 정보 추출
        img_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', guide_text, re.I)
        
        # 텍스트 설명 먼저 출력
        clean_guide_text = re.sub(r'\[이미지:\s*(https?:\/\/[^\s\]]+)\]', '', guide_text)
        st.markdown(clean_guide_text, unsafe_allow_html=True)
        
        # 바로 다음에 이미지 그리드 출력
        if img_patterns:
            st.divider()
            cols = st.columns(2)
            for idx, (name, url) in enumerate(img_patterns):
                with cols[idx % 2]:
                    st.image(url.strip(), use_container_width=True)
                    st.markdown(f"<div style='text-align:center; font-weight:bold; color:#1d4ed8;'>{name}</div>", unsafe_allow_html=True)

    if st.session_state.shared_link:
        st.info(f"🔗 환자 전달용 링크: {st.session_state.shared_link}")

    if st.button("🔄 다음 환자 진료"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

import streamlit as st
import google.generativeai as genai 
import re
import datetime
import uuid
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 설정 및 세션 초기화 (AttributeError 방지) ---
st.set_page_config(page_title="한방 임상 보조 시스템", page_icon="🩺", layout="centered")

# 세션 상태 강제 초기화
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
                # HTML 태그가 텍스트로 보이지 않도록 처리
                display_html = row_data[4].replace("```html", "").replace("```", "")
                st.markdown(display_html, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        except: st.error("기록을 찾을 수 없습니다.")
    if st.button("🏠 메인으로"):
        st.query_params.clear()
        st.rerun()
    st.stop()

# --- 4. 커스텀 CSS (큰 파란색 버튼 및 리포트 스타일) ---
st.markdown("""
    <style>
    .stCard { background-color: #ffffff; border-radius: 16px; padding: 25px; border: 1px solid #e2e8f0; margin-bottom: 20px; }
    
    /* 제목 스타일: 원장님이 요청하신 큰 파란 제목 */
    .result-title { 
        color: #1d4ed8 !important; 
        font-size: 1.5rem !important; 
        font-weight: 800 !important; 
        border-bottom: 3px solid #1d4ed8; 
        padding-bottom: 8px; 
        margin-top: 30px; 
        margin-bottom: 15px; 
    }
    
    /* 버튼 스타일: 크고 선명한 파란색 */
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

# --- 5. UI 로직 ---

# 1단계: 입력
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
                
                PROMPT = f"""환자: {name}, 증상: {raw_text}\n
                [지침]: 정확한 변증을 위해 질문 5개 이상 필수 생성. 
                질문은 반드시 한 줄에 하나씩 ?로 끝나게 작성할 것.
                [추가 확인 사항]: 질문들..."""
                
                try:
                    res = model.generate_content(PROMPT).text
                    qs = [q.strip() for q in re.split(r'\n|(?<=\?)\s*', res.split("[추가 확인 사항]")[-1]) if '?' in q]
                    # 질문 5개 보장 로직
                    defaults = ["증상 발생 시기는?", "통증 양상은?", "소화 상태는?", "수면 상태는?", "악화 요인은?"]
                    st.session_state.follow_up_questions = (qs + defaults)[:max(5, len(qs))]
                    st.session_state.raw_text = raw_text
                    st.session_state.step = "verify"
                    st.rerun()
                except: st.error("API 연결 오류")
    st.markdown('</div>', unsafe_allow_html=True)

# 2단계: 문진
elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("🔍 정밀 문진")
    # AttributeError 방지를 위해 리스트 존재 여부 확인
    questions = st.session_state.get('follow_up_questions', [])
    for i, q in enumerate(questions):
        st.markdown(f'<div class="q-item">{i+1}. {q}</div>', unsafe_allow_html=True)
        st.session_state.responses[f"q_{i}"] = st.text_input(f"답변 {i+1}", key=f"ans_{i}")
    
    if st.button("✅ 최종 처방 생성 및 저장"):
        st.session_state.step = "result"
        st.rerun()

# 3단계: 결과 (수정된 렌더링 및 제목 반영)
elif st.session_state.step == "result":
    if not st.session_state.final_plan:
        with st.spinner("최종 진단 리포트 작성 중..."):
            p = st.session_state.patient_info
            ans_str = "\n".join([f"Q: {q} A: {st.session_state.responses.get(f'q_{i}', '')}" for i, q in enumerate(st.session_state.follow_up_questions)])
            db = st.secrets.get("TREATMENT_DB", "")
            
            FINAL_PROMPT = f"""
            [TREATMENT_DB]: {db}
            환자: {p['name']}, 주소증: {st.session_state.raw_text}, 답변: {ans_str}
            
            [지침]:
            1. 모든 대제목은 반드시 <div class='result-title'>제목명</div> 태그로 감쌀 것.
            2. 출력물에 마크다운 코드 블록(```html)을 사용하지 말고 순수 HTML 태그와 텍스트만 출력할 것.
            3. **[의심되는 질환명]**: 양방(KCD) 및 한방병명 병기.
            4. **[차트 정리]**: 의료기록 원칙 준수 (침, 뜸, 부항 치료 포함).
            5. **[치료 혈자리]**: DB 기반 취혈(동측/대측 명시).
            6. **[혈자리 가이드]**: '이름 [이미지: URL]' 형식.
            """
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"][0])
            model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
            st.session_state.final_plan = model.generate_content(FINAL_PROMPT).text
            
            # 구글 시트 저장 및 링크 생성
            new_id = str(uuid.uuid4())[:8]
            sheet = get_storage_sheet()
            if sheet:
                sheet.append_row([new_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), f"{p['name']}", "자동", st.session_state.final_plan])
                st.session_state.shared_link = f"{MY_APP_URL}?view={new_id}"

    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    # 2번 요청사항 반영: (이름) 최종진단
    st.subheader(f"📋 {st.session_state.patient_info['name']} 최종진단")
    
    # 1번 요청사항 반영: HTML 태그 노출 방지 전처리
    clean_html = st.session_state.final_plan.replace("```html", "").replace("```", "")
    main_text = re.sub(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', '', clean_html)
    
    # 최종 출력
    st.markdown(main_text, unsafe_allow_html=True)
    
    # 이미지 가이드 별도 출력
    img_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', clean_html, re.I)
    if img_patterns:
        st.divider()
        cols = st.columns(2)
        for idx, (name, url) in enumerate(img_patterns):
            with cols[idx % 2]:
                st.image(url.strip(), use_container_width=True)
                st.markdown(f"<div style='text-align:center; font-weight:bold;'>{name}</div>", unsafe_allow_html=True)

    if st.session_state.shared_link:
        st.info(f"🔗 공유 링크: {st.session_state.shared_link}")

    if st.button("🔄 다음 환자 진료"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

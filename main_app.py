import streamlit as st
import google.generativeai as genai 
import re
import datetime
import uuid
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 설정 및 공유 주소 설정 ---
st.set_page_config(page_title="한방 임상 보조 시스템", page_icon="🩺", layout="centered")

# 스트림릿 배포 후 부여받은 실제 URL을 입력하세요 (예: https://your-app.streamlit.app/)
MY_APP_URL = "https://idstring.streamlit.app/" 

# --- 2. 세션 상태 초기화 (에러 방지용) ---
if 'step' not in st.session_state: st.session_state.step = "input"
if 'patient_info' not in st.session_state: st.session_state.patient_info = {"name": "", "gender": "미선택", "birth_year": ""}
if 'follow_up_questions' not in st.session_state: st.session_state.follow_up_questions = []
if 'responses' not in st.session_state: st.session_state.responses = {}
if 'final_plan' not in st.session_state: st.session_state.final_plan = ""
if 'shared_link' not in st.session_state: st.session_state.shared_link = ""

# --- 3. 구글 시트 연동 함수 ---
def get_storage_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
    except: return None

# --- 4. [공유 페이지 모드] 확인 ---
query_params = st.query_params
shared_id = query_params.get("view")

if shared_id:
    sheet = get_storage_sheet()
    if sheet:
        try:
            cell = sheet.find(shared_id)
            if cell:
                row_data = sheet.row_values(cell.row)
                st.markdown(f"### 🩺 {row_data[2]} 진료 결과")
                st.markdown('<div style="background-color: white; padding: 25px; border-radius: 16px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">', unsafe_allow_html=True)
                st.markdown(row_data[4], unsafe_allow_html=True) # HTML 스타일 적용된 본문
                st.markdown('</div>', unsafe_allow_html=True)
            else: st.error("기록을 찾을 수 없습니다.")
        except: st.error("데이터 로딩 중 오류 발생")
    if st.button("🏠 내 진료실 메인으로 이동"):
        st.query_params.clear()
        st.rerun()
    st.stop()

# --- 5. 커스텀 CSS (큰 파란색 버튼 및 제목 스타일) ---
st.markdown("""
    <style>
    /* 카드 디자인 */
    .stCard { background-color: #ffffff; border-radius: 16px; padding: 25px; border: 1px solid #e2e8f0; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    
    /* 결과 화면 대제목 스타일 (파란색, 큰 폰트) */
    .result-title { 
        color: #1d4ed8; 
        font-size: 1.6rem; 
        font-weight: 800; 
        border-bottom: 3px solid #1d4ed8; 
        padding-bottom: 8px; 
        margin-top: 35px; 
        margin-bottom: 15px; 
    }
    
    /* 버튼 스타일 (크고 파란색) */
    div.stButton > button {
        background-color: #1d4ed8 !important;
        color: white !important;
        font-size: 1.3rem !important;
        font-weight: 800 !important;
        height: 4em !important;
        width: 100% !important;
        border-radius: 15px !important;
        border: none !important;
        box-shadow: 0 4px 15px rgba(29, 78, 216, 0.3) !important;
        transition: all 0.2s ease;
    }
    div.stButton > button:hover {
        background-color: #1e40af !important;
        transform: translateY(-2px);
    }
    
    .q-item { background-color: #f8fafc; padding: 15px; border-radius: 10px; border-left: 5px solid #3b82f6; margin-top: 10px; font-weight: 500; }
    .share-box { background-color: #f1f5f9; border: 1px solid #cbd5e1; padding: 15px; border-radius: 12px; margin-top: 25px; }
    </style>
    """, unsafe_allow_html=True)

def calculate_age(birth_year):
    try: return 2025 - int(birth_year) + 1
    except: return "미상"

# --- 6. 단계별 UI 로직 ---

# 1단계: 정보 입력
if st.session_state.step == "input":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("👤 환자 정보 및 증상 입력")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1: name = st.text_input("이름", placeholder="성함")
    with c2: gender = st.selectbox("성별", ["미선택", "남성", "여성"])
    with c3: birth_year = st.text_input("출생년도", placeholder="예: 1985")
    raw_text = st.text_area("주소증 입력", height=150, placeholder="환자가 호소하는 증상을 입력하세요.")
    
    if st.button("✨ 1차 분석 및 정밀 문진 시작"):
        if raw_text and birth_year:
            st.session_state.patient_info = {"name": name, "gender": gender, "birth_year": birth_year}
            with st.spinner("AI가 분석 중입니다..."):
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"][0])
                model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
                age = calculate_age(birth_year)
                
                PROMPT = f"환자: {name}({age}세)\n증상: {raw_text}\n\n[지침]: 정확한 변증을 위해 질문 5개 이상 필수 생성. 질문마다 ? 포함.\n[SOAP 요약]: ...\n[추가 확인 사항]: 질문들..."
                result = model.generate_content(PROMPT).text
                if "[추가 확인 사항]" in result:
                    parts = result.split("[추가 확인 사항]")
                    qs = [q.strip() for q in re.split(r'\n|(?<=\?)\s*', parts[1]) if '?' in q]
                    # 최소 5개 보장
                    st.session_state.follow_up_questions = (qs + ["발병 시기는 언제인가요?", "통증의 양상은 어떤가요?", "평소 소화는 어떠세요?", "수면 상태는 어떠신가요?", "악화되는 요인이 있나요?"])[:max(5, len(qs))]
                st.session_state.raw_text = raw_text
                st.session_state.step = "verify"
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# 2단계: 정밀 문진 답변
elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("🔍 정밀 문진")
    for i, q in enumerate(st.session_state.follow_up_questions):
        st.markdown(f'<div class="q-item">{q}</div>', unsafe_allow_html=True)
        st.session_state.responses[f"q_{i}"] = st.text_input(f"답변 {i+1}", key=f"ans_{i}")
    
    if st.button("✅ 최종 처방 생성 및 자동 저장"):
        st.session_state.step = "result"
        st.rerun()

# 3단계: 최종 결과 및 공유 링크
elif st.session_state.step == "result":
    if not st.session_state.final_plan:
        with st.spinner("진료기록부 작성 중..."):
            p = st.session_state.patient_info
            age = calculate_age(p['birth_year'])
            ans_str = "\n".join([f"Q: {q} A: {st.session_state.responses.get(f'q_{i}', '')}" for i, q in enumerate(st.session_state.follow_up_questions)])
            db = st.secrets.get("TREATMENT_DB", "")
            
            FINAL_PROMPT = f"""
            [TREATMENT_DB]: {db}
            [환자]: {p['name']}({age}) / [주소증]: {st.session_state.raw_text}\n{ans_str}

            [작성 지침 - 무조건 준수]:
            1. 모든 대제목은 반드시 <div class='result-title'>제목명</div> 형식을 사용할 것.
            2. **[의심되는 질환명]**: 양방병명(KCD 코드)과 한방병명을 나란히 병기.
            3. **[차트 정리]**: 정확성, 상세함, 일관성 원칙 준수. 주소증, 진단명, 치료내용(일반적 침, 뜸, 부항 치료 시행함)을 상세히 기록.
            4. **[치료 혈자리]**: 
               - 오직 [TREATMENT_DB]에 기재된 혈자리만 처방할 것. DB에 없는 처방은 금지.
               - DB에 기재된 '대측 취혈' 또는 '동측 취혈' 원리를 반드시 텍스트로 명시.
            5. **[혈자리 가이드]**: 하단에 '혈자리명 [이미지: URL]' 형식 리스트 작성.
            """
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"][0])
            model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
            st.session_state.final_plan = model.generate_content(FINAL_PROMPT).text
            
            # 구글 시트 자동 저장 및 고유 ID 생성
            new_id = str(uuid.uuid4())[:8]
            sheet = get_storage_sheet()
            if sheet:
                try:
                    sheet.append_row([new_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), f"{p['name']}({age})", "자동발행", st.session_state.final_plan])
                    st.session_state.shared_link = f"{MY_APP_URL}?view={new_id}"
                except: pass

    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader(f"📋 {st.session_state.patient_info['name']} 원장님 진료 리포트")
    
    # 텍스트 출력 (HTML 태그 허용)
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
        st.markdown("🔗 **환자 공유용 자동 생성 링크**")
        st.code(st.session_state.shared_link, language="text")
        st.caption("위 주소를 복사하여 환자분께 전달하세요.")
        st.markdown('</div>', unsafe_allow_html=True)

    if st.button("🔄 다음 환자 진료 시작"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

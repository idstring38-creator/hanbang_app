import streamlit as st
import google.generativeai as genai 
import re
import datetime
import uuid
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 설정 및 공유 주소 ---
st.set_page_config(page_title="한의사 임상 보조 시스템", page_icon="🩺", layout="centered")
MY_APP_URL = "https://idstring.streamlit.app/" 

# --- 2. [중요] 세션 상태 초기화 (AttributeError 방지) ---
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

# --- 4. [공유 모드 확인] ---
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
                st.markdown(row_data[4], unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
            else: st.error("해당 진료 기록을 찾을 수 없습니다.")
        except: st.error("데이터 로딩 중 오류가 발생했습니다.")
    if st.button("🏠 메인으로 이동"):
        st.query_params.clear()
        st.rerun()
    st.stop()

# --- 5. 유틸리티 및 CSS ---
def calculate_age(birth_year):
    try: return 2025 - int(birth_year) + 1
    except: return "미상"

st.markdown("""
    <style>
    .stCard { background-color: #ffffff; border-radius: 16px; padding: 25px; border: 1px solid #e2e8f0; margin-bottom: 20px; }
    .result-title { 
        color: #1e40af; font-size: 1.5rem; font-weight: 800; 
        border-bottom: 2px solid #1e40af; padding-bottom: 5px; margin-top: 30px; margin-bottom: 15px; 
    }
    .q-item { background-color: #fefce8; padding: 12px; border-radius: 10px; color: #854d0e; margin-top: 10px; font-weight: 500; }
    .share-box { background-color: #f1f5f9; border: 1px solid #cbd5e1; padding: 15px; border-radius: 12px; margin-top: 20px; }
    div.stButton > button { border-radius: 12px !important; font-weight: 800 !important; width: 100% !important; height: 3.5em !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 6. 단계별 UI 로직 ---
if st.session_state.step == "input":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("👤 환자 정보 및 증상 입력")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1: name = st.text_input("이름", value=st.session_state.patient_info["name"])
    with c2: gender = st.selectbox("성별", ["미선택", "남성", "여성"], index=["미선택", "남성", "여성"].index(st.session_state.patient_info["gender"]))
    with c3: birth_year = st.text_input("출생년도", value=st.session_state.patient_info["birth_year"])
    raw_text = st.text_area("주소증 입력", height=150)
    
    if st.button("✨ 1차 분석 및 문진 시작 (최소 5개 질문)"):
        if raw_text and birth_year:
            st.session_state.patient_info = {"name": name, "gender": gender, "birth_year": birth_year}
            with st.spinner("AI가 정밀 문진을 준비 중입니다..."):
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"][0])
                model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
                age = calculate_age(birth_year)
                PROMPT = f"환자: {name}({age}세)\n증상: {raw_text}\n\n[지침]: 최종 진단을 위해 필요한 한의학적 문진 질문을 무조건 최소 5개 이상 리스트업 하세요. 질문은 반드시 ?로 끝나야 함.\n[SOAP 요약]: ...\n[추가 확인 사항]: 질문들..."
                result = model.generate_content(PROMPT).text
                if "[추가 확인 사항]" in result:
                    parts = result.split("[추가 확인 사항]")
                    qs = [q.strip() for q in re.split(r'\n|(?<=\?)\s*', parts[1]) if '?' in q]
                    st.session_state.follow_up_questions = (qs + ["발병 시기는 언제인가요?", "통증의 양상은 어떤가요?", "평소 수면은 어떠신가요?"])[:5]
                st.session_state.raw_text = raw_text
                st.session_state.step = "verify"
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("🔍 정밀 문진")
    for i, q in enumerate(st.session_state.follow_up_questions):
        st.markdown(f'<div class="q-item">{q}</div>', unsafe_allow_html=True)
        st.session_state.responses[f"q_{i}"] = st.text_input(f"답변 {i+1}", key=f"ans_{i}")
    
    if st.button("✅ 최종 처방 생성 및 링크 자동발행"):
        st.session_state.step = "result"
        st.rerun()

elif st.session_state.step == "result":
    if not st.session_state.final_plan:
        with st.spinner("진료기록부 작성 및 처방 구성 중..."):
            p = st.session_state.patient_info
            age = calculate_age(p['birth_year'])
            ans_str = "\n".join([f"Q: {q} A: {st.session_state.responses.get(f'q_{i}', '')}" for i, q in enumerate(st.session_state.follow_up_questions)])
            db = st.secrets.get("TREATMENT_DB", "")
            
            FINAL_PROMPT = f"""
            [TREATMENT_DB]: {db}
            [환자]: {p['name']}({age}) / [주소증]: {st.session_state.raw_text}\n{ans_str}

            [작성 지침]:
            1. 모든 대제목은 <div class='result-title'>제목명</div> 태그를 사용할 것.
            2. **[의심되는 질환명]**: 양방병명(KCD 코드 포함)과 한방병명을 반드시 병기.
            3. **[차트 정리]**: 진료기록부 기록 원칙(정확성, 상세함, 일관성) 준수. 주소증, 진단명, 치료내용(일반적 침, 뜸, 부항 치료 시행)을 과장 없이 상세히 기록.
            4. **[치료 혈자리]**: 이름 변경함. 오직 [TREATMENT_DB]에 있는 혈자리만 출력. DB에 명시된 '대측 취혈' 혹은 '동측 취혈' 원칙을 반드시 텍스트로 기재.
            5. **[혈자리 가이드]**: 하단에 '혈자리명 [이미지: URL]' 형식 리스트.
            """
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"][0])
            model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
            st.session_state.final_plan = model.generate_content(FINAL_PROMPT).text
            
            # 구글 시트에 자동 저장 및 링크 생성
            new_id = str(uuid.uuid4())[:8]
            sheet = get_storage_sheet()
            if sheet:
                try:
                    sheet.append_row([new_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), f"{p['name']}({age})", "자동생성", st.session_state.final_plan])
                    st.session_state.shared_link = f"{MY_APP_URL}?view={new_id}"
                except: pass

    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader(f"📋 {st.session_state.patient_info['name']} 원장님 진료 리포트")
    
    # 텍스트 출력
    main_text = re.sub(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', '', st.session_state.final_plan)
    st.markdown(main_text, unsafe_allow_html=True)
    
    # 이미지 가이드 출력
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
        st.markdown("🔗 **환자 전달용 영구 주소** (자동 생성됨)")
        st.code(st.session_state.shared_link, language="text")
        st.markdown('</div>', unsafe_allow_html=True)

    if st.button("🔄 다음 환자 진료"):
        for key in ['step', 'final_plan', 'shared_link', 'responses', 'follow_up_questions']:
            st.session_state[key] = "" if key != 'step' else "input"
            if key in ['responses', 'follow_up_questions']: st.session_state[key] = {} if key=='responses' else []
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

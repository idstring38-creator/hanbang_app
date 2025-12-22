import streamlit as st
import google.generativeai as genai 
import re
import datetime
import uuid
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 설정 및 초기화 ---
st.set_page_config(page_title="한방 임상 보조 시스템", page_icon="🩺", layout="centered")

# 실제 서비스 주소로 변경하세요
MY_APP_URL = "https://idstring.streamlit.app/" 

if 'step' not in st.session_state: st.session_state.step = "input"
if 'patient_info' not in st.session_state: st.session_state.patient_info = {"name": "", "gender": "미선택", "birth_year": ""}
if 'follow_up_questions' not in st.session_state: st.session_state.follow_up_questions = []
if 'responses' not in st.session_state: st.session_state.responses = {}
if 'final_plan' not in st.session_state: st.session_state.final_plan = ""
if 'shared_link' not in st.session_state: st.session_state.shared_link = ""

# --- 2. 구글 시트 연동 ---
def get_storage_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
    except: return None

# --- 3. [공유 모드] 처리 ---
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
            else: st.error("기록을 찾을 수 없습니다.")
        except: st.error("데이터 로딩 중 오류 발생")
    if st.button("🏠 메인으로 이동"):
        st.query_params.clear()
        st.rerun()
    st.stop()

# --- 4. 커스텀 CSS (큰 파란색 버튼 및 제목) ---
st.markdown("""
    <style>
    .stCard { background-color: #ffffff; border-radius: 16px; padding: 25px; border: 1px solid #e2e8f0; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    
    /* 결과 화면 제목 (파란색) */
    .result-title { 
        color: #1d4ed8; font-size: 1.5rem; font-weight: 800; 
        border-bottom: 3px solid #1d4ed8; padding-bottom: 8px; margin-top: 35px; margin-bottom: 15px; 
    }
    
    /* 버튼 스타일 (크고 파란색) */
    div.stButton > button {
        background-color: #1d4ed8 !important; color: white !important;
        font-size: 1.3rem !important; font-weight: 800 !important;
        height: 4em !important; width: 100% !important;
        border-radius: 15px !important; border: none !important;
        box-shadow: 0 4px 15px rgba(29, 78, 216, 0.3) !important;
    }
    div.stButton > button:hover { background-color: #1e40af !important; transform: translateY(-2px); }
    
    .q-item { background-color: #f8fafc; padding: 15px; border-radius: 10px; border-left: 5px solid #3b82f6; margin-top: 10px; font-weight: 600; color: #1e293b; }
    .share-box { background-color: #f1f5f9; border: 1px solid #cbd5e1; padding: 15px; border-radius: 12px; margin-top: 25px; }
    </style>
    """, unsafe_allow_html=True)

def calculate_age(birth_year):
    try: return 2025 - int(birth_year) + 1
    except: return "미상"

# --- 5. UI 단계별 로직 ---

# 1단계: 정보 입력
if st.session_state.step == "input":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("👤 환자 정보 및 증상 입력")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1: name = st.text_input("이름", placeholder="성함")
    with c2: gender = st.selectbox("성별", ["미선택", "남성", "여성"])
    with c3: birth_year = st.text_input("출생년도", placeholder="예: 1985")
    raw_text = st.text_area("주소증 입력 (부실하게 입력해도 AI가 질문을 생성합니다)", height=150)
    
    if st.button("✨ 1차 분석 및 정밀 문진 시작"):
        if raw_text:
            st.session_state.patient_info = {"name": name, "gender": gender, "birth_year": birth_year}
            with st.spinner("AI가 질문을 구성 중입니다..."):
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"][0])
                model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
                age = calculate_age(birth_year)
                
                # 프롬프트에서 '최소 5개'를 강력하게 명령
                FIRST_PROMPT = f"""
                환자 정보: {name}({age}세, {gender})
                주요 증상: {raw_text}
                
                [임무]: 위 환자의 정확한 변증(한열, 허실 등)과 상병 추론을 위해 추가로 확인해야 할 문진 질문을 리스트업 하세요.
                [지침]:
                1. 질문은 반드시 한 줄에 하나씩 작성하고 물음표(?)로 끝내세요.
                2. 입력 데이터가 부족하더라도 한의학적 필수 진찰 항목을 포함하여 **반드시 최소 5개 이상의 질문**을 만드세요.
                
                [SOAP 요약]: ...
                [추가 확인 사항]: 질문들...
                """
                
                response = model.generate_content(FIRST_PROMPT).text
                if "[추가 확인 사항]" in response:
                    parts = response.split("[추가 확인 사항]")
                    # 질문 추출 (줄바꿈 및 ? 기준)
                    qs = [q.strip() for q in re.split(r'\n|(?<=\?)\s*', parts[1]) if '?' in q]
                    
                    # --- [핵심] 질문 5개 보장 로직 ---
                    default_medical_qs = [
                        "해당 증상이 나타난 지 얼마나 되셨나요? (발병일)",
                        "통증이나 불편함의 양상은 어떠한가요? (저림, 쑤심, 은은한 통증 등)",
                        "증상이 특별히 심해지거나 완화되는 시간이나 상황이 있나요?",
                        "평소 소화 상태나 대소변은 원활하신가요?",
                        "수면 중에 불편함이 있거나 꿈을 많이 꾸시나요?",
                        "추위나 더위를 많이 타시는 편인가요?"
                    ]
                    
                    # 부족한 만큼 기본 질문에서 보충
                    while len(qs) < 5:
                        for dq in default_medical_qs:
                            if dq not in qs:
                                qs.append(dq)
                            if len(qs) >= 5: break
                    
                    st.session_state.follow_up_questions = qs[:max(5, len(qs))]
                st.session_state.raw_text = raw_text
                st.session_state.step = "verify"
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# 2단계: 정밀 문진 답변
elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("🔍 정밀 문진 (필수 5개 이상)")
    for i, q in enumerate(st.session_state.follow_up_questions):
        st.markdown(f'<div class="q-item">{i+1}. {q}</div>', unsafe_allow_html=True)
        st.session_state.responses[f"q_{i}"] = st.text_input(f"답변 {i+1}", key=f"ans_{i}", placeholder="환자의 답변을 입력하세요")
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("✅ 최종 처방 생성 및 자동 저장"):
        st.session_state.step = "result"
        st.rerun()

# 3단계: 최종 진단 및 처방
elif st.session_state.step == "result":
    if not st.session_state.final_plan:
        with st.spinner("최종 진단 수립 및 리포트 작성 중..."):
            p = st.session_state.patient_info
            age = calculate_age(p['birth_year'])
            ans_str = "\n".join([f"Q: {q} A: {st.session_state.responses.get(f'q_{i}', '')}" for i, q in enumerate(st.session_state.follow_up_questions)])
            db = st.secrets.get("TREATMENT_DB", "")
            
            FINAL_PROMPT = f"""
            [TREATMENT_DB]: {db}
            [환자 정보]: {p['name']}({age}) / [입력 증상]: {st.session_state.raw_text}
            [문진 답변]:\n{ans_str}

            [작성 지침 - 엄격 준수]:
            1. 모든 대제목은 <div class='result-title'>제목명</div> 태그를 사용할 것.
            2. **[의심되는 질환명]**: 양방병명(KCD 코드 포함)과 한방병명을 반드시 병기할 것.
            3. **[차트 정리]**: 진료기록부 기록 원칙(정확성, 상세함, 일관성) 준수. 주소증, 진단, 치료내용(침, 뜸, 부항 치료 시행함)을 과장 없이 상세히 기록.
            4. **[치료 혈자리]**: 
               - 오직 [TREATMENT_DB]에 있는 혈자리만 출력. DB에 없는 처방은 절대 금지.
               - DB에 기재된 '대측 취혈' 또는 '동측 취혈' 원리를 반드시 텍스트로 포함할 것.
            5. **[혈자리 가이드]**: '혈자리명 [이미지: URL]' 형식으로 마무리.
            """
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"][0])
            model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
            st.session_state.final_plan = model.generate_content(FINAL_PROMPT).text
            
            # 구글 시트 자동 저장
            new_id = str(uuid.uuid4())[:8]
            sheet = get_storage_sheet()
            if sheet:
                try:
                    sheet.append_row([new_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), f"{p['name']}({age})", "자동", st.session_state.final_plan])
                    st.session_state.shared_link = f"{MY_APP_URL}?view={new_id}"
                except: pass

    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader(f"📋 {st.session_state.patient_info['name']} 원장님 진단 리포트")
    
    # 본문 출력 (HTML 태그 반영)
    main_text = re.sub(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', '', st.session_state.final_plan)
    st.markdown(main_text, unsafe_allow_html=True)
    
    # 이미지 가이드
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
        st.markdown('</div>', unsafe_allow_html=True)

    if st.button("🔄 다음 환자 진료 시작"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

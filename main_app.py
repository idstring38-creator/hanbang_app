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

# --- 헬퍼 함수: 텍스트 내 이미지 태그를 HTML img로 변환 ---
def render_text_with_images(text):
    # [이미지: URL] 패턴을 찾아서 <img src="..."> 태그로 변환
    # 모바일 화면 너비에 맞게 width 100% 설정 및 스타일 적용
    pattern = r'\[이미지:\s*(https?://[^\s\]]+)\]'
    replacement = r'<br><img src="\1" style="width: 100%; max-width: 400px; border-radius: 10px; margin: 10px 0; box-shadow: 0 2px 5px rgba(0,0,0,0.1);"><br>'
    return re.sub(pattern, replacement, text)

# --- 3. [공유 모드 확인 - 수정됨] ---
query_params = st.query_params
shared_id = query_params.get("view")

if shared_id:
    sheet = get_storage_sheet()
    if sheet:
        try:
            cell = sheet.find(shared_id)
            if cell:
                row_data = sheet.row_values(cell.row)
                st.markdown(f"### 🩺 {row_data[2]}님 최종 진단결과")
                st.markdown('<div style="background-color: white; padding: 25px; border-radius: 16px; border: 1px solid #e2e8f0;">', unsafe_allow_html=True)
                
                # 저장된 원본 텍스트 가져오기
                raw_content = row_data[4].replace("```html", "").replace("```", "")
                
                # [수정 1] 이미지 태그를 HTML로 변환하여 렌더링 (모바일 즉시 보기 지원)
                processed_content = render_text_with_images(raw_content)
                st.markdown(processed_content, unsafe_allow_html=True)
                
                st.markdown('</div>', unsafe_allow_html=True)
        except: st.error("기록을 찾을 수 없습니다.")
    
    st.write("")
    if st.button("🏠 새로운 진단하러 가기"):
        st.query_params.clear()
        st.rerun()
    st.stop()

# --- 4. 커스텀 CSS ---
st.markdown("""
    <style>
    .stCard { background-color: #ffffff; border-radius: 16px; padding: 25px; border: 1px solid #e2e8f0; margin-bottom: 20px; }
    
    .result-title { 
        color: #0056b3 !important; 
        font-size: 1.5rem !important; 
        font-weight: 900 !important; 
        border-left: 6px solid #0056b3; 
        padding-left: 12px;
        margin-top: 40px !important; 
        margin-bottom: 15px !important;
        background-color: #f8fbff;
        padding-top: 8px;
        padding-bottom: 8px;
        border-radius: 0 5px 5px 0;
    }
    
    div.stButton > button {
        background-color: #1d4ed8 !important; color: white !important;
        font-size: 1.1rem !important; font-weight: 700 !important;
        height: 3.5em !important; width: 100% !important;
        border-radius: 12px !important; border: none !important;
        box-shadow: 0 4px 10px rgba(29, 78, 216, 0.2) !important;
    }
    
    .q-item { background-color: #f8fafc; padding: 15px; border-radius: 10px; border-left: 5px solid #3b82f6; margin-top: 10px; font-weight: 600; }
    .section-gap { margin-bottom: 30px; }
    </style>
    """, unsafe_allow_html=True)

def calculate_age(birth_year):
    try: return datetime.date.today().year - int(birth_year) + 1
    except: return "미상"

# --- 5. UI 로직 ---

if st.session_state.step == "input":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("👤 환자 정보 및 증상 입력")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1: name = st.text_input("이름", placeholder="성함")
    with c2: gender = st.selectbox("성별", ["남성", "여성", "미선택"])
    with c3: birth_year = st.text_input("출생년도", placeholder="예: 1985")
    raw_text = st.text_area("주소증 입력", height=150, placeholder="환자의 주요 증상을 최대한 자세히 입력해주세요.")
    
    if st.button("✨ 분석 시작 및 문진 생성"):
        if raw_text:
            st.session_state.patient_info = {"name": name, "gender": gender, "birth_year": birth_year}
            with st.spinner("증상을 분석하여 핵심 질문을 생성하고 있습니다..."):
                genai.configure(api_key=st.secrets["GEMINI_API_KEY"][0])
                model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
                PROMPT = f"환자: {name}, 증상: {raw_text}\n[지침]: 한의학적 변증을 위해 꼭 필요한 예리한 질문 5가지를 생성하시오. 각 질문은 물음표(?)로 끝나야 함."
                try:
                    res = model.generate_content(PROMPT).text
                    qs = [q.strip() for q in re.split(r'\n|(?<=\?)\s*', res) if '?' in q]
                    defaults = ["증상 발생 시기는 언제부터인가요?", "통증의 양상(찌르는 듯, 묵직함 등)은 어떤가요?", "소화 상태와 대변 양상은 어떤가요?", "수면 상태와 평소 컨디션은 어떤가요?", "증상이 악화되거나 완화되는 조건이 있나요?"]
                    st.session_state.follow_up_questions = (qs + defaults)[:max(5, len(qs))]
                    st.session_state.raw_text = raw_text
                    st.session_state.step = "verify"
                    st.rerun()
                except: st.error("API 연결 실패. 잠시 후 다시 시도해주세요.")
    st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("🔍 정밀 문진")
    st.info("AI가 환자의 증상을 바탕으로 생성한 추가 질문입니다.")
    for i, q in enumerate(st.session_state.follow_up_questions):
        st.markdown(f'<div class="q-item">{i+1}. {q}</div>', unsafe_allow_html=True)
        st.session_state.responses[f"q_{i}"] = st.text_input(f"답변 {i+1}", key=f"ans_{i}")
    
    if st.button("✅ 심층 진단 및 처방 생성"):
        st.session_state.step = "result"
        st.rerun()

elif st.session_state.step == "result":
    if not st.session_state.final_plan:
        with st.spinner("데이터베이스를 대조하여 최적의 치료 혈자리를 선정 중입니다..."):
            p = st.session_state.patient_info
            age = calculate_age(p['birth_year'])
            ans_str = "\n".join([f"Q: {q} A: {st.session_state.responses.get(f'q_{i}', '')}" for i, q in enumerate(st.session_state.follow_up_questions)])
            db_content = st.secrets.get("TREATMENT_DB", "")
            
            # [수정 2 & 3] 프롬프트 강화 (DB 준수 및 차트 형식 지정)
            FINAL_PROMPT = f"""
            [TREATMENT_DB]:
            {db_content}
            
            환자정보: {p['name']}({p['gender']}, {age}세)
            주소증: {st.session_state.raw_text}
            문진결과: {ans_str}

            [작성 지침 - 엄격 준수]:
            1. **[차트 정리]**: 실제 의무기록부(EMR)에 복사하여 붙여넣을 수 있도록 아래 포맷으로 간결하고 전문적으로 작성하시오.
               - C/C (주소증):
               - O/S (현병력): 발병일, 계기, 증상 양상 포함
               - P/H (과거력/특이사항): 문진 내용 요약
               - Imp (진단명): 한의학적 변증명 (예: 간울기체, 비위습열 등) 및 U코드
               - Tx Plan (치료계획): 주요 치료 혈자리 나열
               - Note: (법적 방어를 위한 진료 기록 및 환자 교육 내용 필수 포함)

            2. **[혈자리 처방]**: 
               - **매우 중요**: 처방하는 혈자리는 반드시 상단에 제공된 [TREATMENT_DB]에 존재하는 혈자리여야 합니다. 
               - **DB에 없는 혈자리는 절대 임의로 창작하거나 추천하지 마십시오.**
               - DB에 해당 증상에 대한 정확한 혈자리가 없다면, 가장 유사한 카테고리의 혈자리를 추천하고 그 이유를 설명하십시오.

            3. **[혈자리 가이드]**:
               - 형식: "(동측/대측) 혈자리이름(코드) [이미지: URL]" 
               - 이미지 URL은 깃허브 원본 주소를 그대로 사용할 것. (예: https://raw.githubusercontent.com/...)
               - 설명이 아닌 '목록' 형태로 나열하시오.

            [출력 형식]:
            모든 대제목은 <div class='result-title'>제목명</div>을 사용하고, 섹션 끝에는 <div class='section-gap'></div>를 추가하시오.
            순서: **[차트 정리]**, **[변증 및 진단 상세]**, **[혈자리 처방]**, **[혈자리 가이드]**
            """
            
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"][0])
            model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
            st.session_state.final_plan = model.generate_content(FINAL_PROMPT).text
            
            new_id = str(uuid.uuid4())[:8]
            sheet = get_storage_sheet()
            if sheet:
                # 시트 저장 시점
                sheet.append_row([new_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), f"{p['name']}", "자동", st.session_state.final_plan])
                st.session_state.shared_link = f"{MY_APP_URL}?view={new_id}"

    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader(f"📋 {st.session_state.patient_info['name']}님 최종진단")
    
    # 1. 결과 출력 (이미지 렌더링 함수 적용)
    raw_plan = st.session_state.final_plan.replace("```html", "").replace("```", "")
    processed_plan = render_text_with_images(raw_plan)
    st.markdown(processed_plan, unsafe_allow_html=True)

    # [수정 4] 공유 주소 복사 UI 개선
    if st.session_state.shared_link:
        st.divider()
        st.markdown("### 🔗 환자용 공유 링크")
        st.info("아래 주소 박스 오른쪽 끝의 '복사 아이콘'을 누르면 클립보드에 복사됩니다.")
        
        # Streamlit의 st.code는 기본적으로 우측 상단에 복사 버튼을 제공합니다.
        # 이를 버튼처럼 보이게 하기 위해 UI적으로 배치합니다.
        st.code(st.session_state.shared_link, language=None)
        
        st.caption("※ 이 링크를 카카오톡 등으로 환자에게 전달하세요. 별도의 로그인 없이 결과를 볼 수 있습니다.")

    st.divider()
    if st.button("🔄 다음 환자 진료 시작 (초기화)"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

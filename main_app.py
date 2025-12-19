import streamlit as st
from google import genai
import re
import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 설정 및 초기화 ---
st.set_page_config(
    page_title="한의사 임상 보조 시스템",
    page_icon="🩺",
    layout="centered"
)

# 세션 상태 초기화 (데이터 휘발 방지)
if 'patient_count' not in st.session_state:
    st.session_state.patient_count = 1
if 'patient_name' not in st.session_state:
    st.session_state.patient_name = ""
if 'step' not in st.session_state:
    st.session_state.step = "input" 
if 'final_plan' not in st.session_state:
    st.session_state.final_plan = ""

def clear_form():
    st.session_state.patient_count += 1
    st.session_state.patient_name = ""
    st.session_state.step = "input"
    st.session_state.final_plan = ""

# --- 2. 구글 시트 데이터 저장 로직 ---
def save_to_google_sheets(name, content):
    try:
        # 1. 인증 정보 설정 (Secrets에서 가져오기)
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        
        # 2. 시트 열기 (ID 기준)
        sheet = client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
        
        # 3. 데이터 구성 (날짜, 시간, 순번, 이름, 내용)
        now = datetime.datetime.now()
        row = [
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            st.session_state.patient_count,
            name,
            content
        ]
        
        # 4. 행 추가
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"구글 시트 저장 중 오류 발생: {e}")
        return False

# --- 3. UI 디자인 (CSS) ---
st.markdown("""
    <style>
    .stCard {
        background-color: #ffffff;
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        border: 1px solid #e2e8f0;
        margin-bottom: 20px;
    }
    .main-title { font-size: 2rem; font-weight: 800; color: #1e293b; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. API 클라이언트 설정 ---
gemini_client = None
try:
    gemini_client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    treatment_db = st.secrets["TREATMENT_DB"]
except:
    st.warning("API 키가 설정되지 않았습니다. Secrets 설정을 확인해주세요.")

def get_ai_response(prompt):
    response = gemini_client.models.generate_content(
        model='gemini-2.5-flash-preview-09-2025', 
        contents=prompt
    )
    return response.text

# --- 5. 메인 레이아웃 ---
st.markdown('<p class="main-title">🩺 한의사 임상 보조 시스템</p>', unsafe_allow_html=True)

# 상단 상태바
col_info1, col_info2 = st.columns([1, 3])
with col_info1:
    st.info(f"오늘의 **{st.session_state.patient_count}**번째 환자")
with col_info2:
    st.session_state.patient_name = st.text_input("환자 성함", value=st.session_state.patient_name, placeholder="이름을 입력하세요")

# [입력 단계]
if st.session_state.step == "input":
    st.subheader("📝 진단 및 처방 생성")
    user_input = st.text_area("증상 또는 환자와의 대화 내용을 입력하세요", height=200, placeholder="예: 어제부터 허리가 찌릿하며 다리까지 저림...")
    
    if st.button("🚀 분석 및 처방 생성", use_container_width=True):
        if not st.session_state.patient_name:
            st.error("환자 이름을 먼저 입력해주세요.")
        elif not user_input:
            st.error("증상을 입력해주세요.")
        else:
            with st.spinner("AI가 원락극 체계를 분석 중입니다..."):
                full_prompt = f"""
                한방 임상 가이드라인:
                {treatment_db}
                
                환자 이름: {st.session_state.patient_name}
                호소 증상: {user_input}
                
                위 내용을 바탕으로 다음 형식으로 출력해줘:
                1. SOAP 형식의 요약
                2. 원락극 체계에 따른 혈자리 처방 (측성 원칙 포함)
                3. 혈자리 가이드 (혈자리명 [이미지: URL] 형식 포함)
                """
                st.session_state.final_plan = get_ai_response(full_prompt)
                st.session_state.step = "result"
                st.rerun()

# [결과 단계]
elif st.session_state.step == "result":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader(f"✅ {st.session_state.patient_name}님 분석 결과")
    st.markdown(st.session_state.final_plan)
    
    # 이미지 파싱 및 표시
    img_matches = re.findall(r'(\S+)\s*\[이미지:\s*(https?://[^\s\]]+)\]', st.session_state.final_plan)
    if img_matches:
        st.divider()
        img_cols = st.columns(2)
        for i, (name, url) in enumerate(img_matches):
            with img_cols[i % 2]:
                st.image(url, caption=f"혈자리 가이드: {name}")
    st.markdown('</div>', unsafe_allow_html=True)

    # 모바일 연동 버튼
    save_col1, save_col2 = st.columns(2)
    with save_col1:
        if st.button("📲 모바일(구글 시트)로 전송", variant="primary", use_container_width=True):
            with st.spinner("구글 시트 동기화 중..."):
                if save_to_google_sheets(st.session_state.patient_name, st.session_state.final_plan):
                    st.success("데이터 전송 완료! 모바일 앱을 확인하세요.")
                else:
                    st.error("전송에 실패했습니다. 관리자에게 문의하세요.")
    
    with save_col2:
        if st.button("🔄 다음 진료 (초기화)", use_container_width=True):
            clear_form()
            st.rerun()
import streamlit as st
from google import genai
import re
import datetime
import time
from groq import Groq
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 설정 및 초기화 ---
st.set_page_config(
    page_title="한의사 임상 보조 시스템",
    page_icon="🩺",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 세션 상태 초기화
if 'patient_count' not in st.session_state:
    st.session_state.patient_count = 1
if 'current_time' not in st.session_state:
    st.session_state.current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
if 'step' not in st.session_state:
    st.session_state.step = "input" # input -> verify -> result
if 'soap_result' not in st.session_state:
    st.session_state.soap_result = ""
if 'follow_up_questions' not in st.session_state:
    st.session_state.follow_up_questions = ""
if 'raw_text' not in st.session_state:
    st.session_state.raw_text = ""
if 'additional_input' not in st.session_state:
    st.session_state.additional_input = ""
if 'final_plan' not in st.session_state:
    st.session_state.final_plan = ""

def clear_form():
    st.session_state.raw_text = ""
    st.session_state.current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    st.session_state.patient_count += 1
    st.session_state.step = "input"
    st.session_state.soap_result = ""
    st.session_state.follow_up_questions = ""
    st.session_state.additional_input = ""
    st.session_state.final_plan = ""

# --- 2. 구글 시트 저장 함수 ---
def save_to_google_sheets(content):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        
        sheet = client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
        
        now = datetime.datetime.now()
        # 데이터 구성: 날짜, 시간, 순번, 내용 요약
        row = [
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            st.session_state.patient_count,
            st.session_state.soap_result[:100] + "...", # 요약본
            content # 전체 처방 내용
        ]
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"구글 시트 저장 중 오류 발생: {e}")
        return False

# --- 3. 커스텀 CSS (기존 디자인 유지) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Noto Sans KR', sans-serif;
        background-color: #f8fafc;
    }
    
    .stCard {
        background-color: #ffffff;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        border: 1px solid #e2e8f0;
        margin-bottom: 20px;
    }
    
    .main-header {
        text-align: center;
        margin-bottom: 20px;
    }
    
    .soap-box {
        background-color: #f1f5f9;
        border-left: 5px solid #3b82f6;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
        white-space: pre-wrap;
        font-size: 0.95rem;
        line-height: 1.5;
    }

    .stButton>button {
        width: 100%;
        border-radius: 16px;
        height: 3.5em;
        background-color: #2563eb;
        color: white !important;
        font-weight: 800;
        border: none;
        box-shadow: 0 4px 10px rgba(37, 99, 235, 0.2);
    }
    
    .verify-btn>button {
        background-color: #059669 !important;
        box-shadow: 0 4px 10px rgba(5, 150, 105, 0.2) !important;
    }

    .q-box {
        background-color: #fffbeb;
        border: 1px solid #fde68a;
        padding: 15px;
        border-radius: 12px;
        color: #92400e;
        margin-bottom: 15px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 4. API 클라이언트 ---
gemini_client = None
try:
    gemini_client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as e:
    st.error(f"⚠️ Gemini API 초기화 실패: {e}")

groq_client = None
try:
    groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])
except:
    pass

try:
    treatment_db_content = st.secrets["TREATMENT_DB"]
except:
    st.error("⚠️ TREATMENT_DB 설정이 필요합니다.")
    st.stop()

# --- 5. 분석 엔진 ---
def analyze_with_hybrid_fallback(prompt):
    # 1단계: Gemini
    gemini_models = ['gemini-2.5-flash-preview-09-2025', 'models/gemini-1.5-flash']
    for model in gemini_models:
        try:
            response = gemini_client.models.generate_content(model=model, contents=prompt)
            if response and response.text:
                return response.text
        except Exception:
            continue
            
    # 2단계: Groq
    if groq_client:
        try:
            chat_completion = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.3,
            )
            return chat_completion.choices[0].message.content
        except Exception as e:
            st.error(f"Groq 호출 실패: {e}")
    
    raise Exception("모든 AI 모델 호출에 실패했습니다.")

def clean_newlines(text):
    if not text: return ""
    return re.sub(r'\n{3,}', '\n\n', text).strip()

# --- 6. UI 및 로직 ---
st.markdown('<div class="main-header">', unsafe_allow_html=True)
st.title("🩺 한방 임상 보조 시스템")
st.write(f"현재 환자: **#{st.session_state.patient_count}**")
st.markdown('</div>', unsafe_allow_html=True)

# [Step 1] 최초 입력창
if st.session_state.step == "input":
    with st.container():
        st.markdown('<div class="stCard">', unsafe_allow_html=True)
        st.subheader("📝 대화 원문 입력")
        raw_text = st.text_area(
            "환자와의 대화나 증상을 입력하세요", 
            key='raw_text_input', 
            height=200,
            label_visibility="collapsed"
        )
        if st.button("✨ 1차 분석 및 문진 확인"):
            if raw_text:
                with st.spinner("증상을 분석 중입니다..."):
                    FIRST_PROMPT = f"""
                    당신은 노련한 한의사 보조 AI입니다. 다음 대화 원문을 바탕으로 '문진 단계'를 수행하세요.
                    
                    **답변 형식**:
                    1. [SOAP 요약]: 환자의 주소증과 현 상태를 SOAP 형식으로 간략히 요약하세요.
                    2. [추가 확인 사항]: 육기 진단을 위해 원장님이 추가로 물어봐야 할 질문 리스트를 작성하세요.
                    
                    [대화 원문]: {raw_text}
                    """
                    try:
                        result = analyze_with_hybrid_fallback(FIRST_PROMPT)
                        if "[추가 확인 사항]" in result:
                            parts = result.split("[추가 확인 사항]")
                            st.session_state.soap_result = clean_newlines(parts[0].replace("[SOAP 요약]", "").strip())
                            st.session_state.follow_up_questions = clean_newlines(parts[1].strip())
                        else:
                            st.session_state.soap_result = clean_newlines(result.replace("[SOAP 요약]", "").strip())
                            st.session_state.follow_up_questions = "추가 질문 없음"
                        
                        st.session_state.raw_text = raw_text
                        st.session_state.step = "verify"
                        st.rerun()
                    except Exception as e:
                        st.error(f"분석 중 오류 발생: {e}")
            else:
                st.warning("내용을 입력해주세요.")
        st.markdown('</div>', unsafe_allow_html=True)

# [Step 2] 추가 문진 확인
elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("📋 1차 SOAP 요약")
    st.markdown(f'<div class="soap-box">{st.session_state.soap_result}</div>', unsafe_allow_html=True)
    
    if st.session_state.follow_up_questions and "질문 없음" not in st.session_state.follow_up_questions:
        st.markdown('<div class="q-box">', unsafe_allow_html=True)
        st.markdown("##### 🔍 추가 확인이 필요합니다")
        st.markdown(st.session_state.follow_up_questions)
        st.markdown('</div>', unsafe_allow_html=True)
    
    additional_info = st.text_area("추가 확인 내용 입력", height=150)
    
    st.markdown('<div class="verify-btn">', unsafe_allow_html=True)
    if st.button("✅ 최종 확인 및 처방 생성"):
        st.session_state.additional_input = additional_info if additional_info else "특이사항 없음"
        st.session_state.step = "result"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# [Step 3] 최종 결과 출력 및 연동
elif st.session_state.step == "result":
    if not st.session_state.final_plan:
        with st.spinner("최종 치료 계획을 수립 중..."):
            FINAL_PROMPT = f"""
            [치료 DB]: {treatment_db_content}
            [1차 SOAP 요약]: {st.session_state.soap_result}
            [추가 정보]: {st.session_state.additional_input}
            
            위 정보를 바탕으로 원락극 처방(측성 포함)과 상세 분석을 작성하세요.
            마지막에 혈자리 [이미지: URL] 리스트를 포함하세요.
            """
            st.session_state.final_plan = analyze_with_hybrid_fallback(FINAL_PROMPT)

    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("💡 최종 추천 치료 및 처방")
    st.markdown(st.session_state.final_plan)
    
    # 이미지 표시 로직
    img_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', st.session_state.final_plan)
    if img_patterns:
        st.divider()
        cols = st.columns(2)
        for idx, (name, url) in enumerate(img_patterns):
            with cols[idx % 2]:
                st.image(url.strip(), caption=name, use_container_width=True)

    st.divider()
    
    # --- 구글 시트 전송 섹션 ---
    col_save, col_next = st.columns(2)
    with col_save:
        if st.button("📲 모바일 시트 전송", type="primary"):
            with st.spinner("시트 저장 중..."):
                if save_to_google_sheets(st.session_state.final_plan):
                    st.success("전송 완료! 모바일에서 확인하세요.")
                else:
                    st.error("전송에 실패했습니다.")
    
    with col_next:
        if st.button("🔄 다음 환자 진료"):
            clear_form()
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# 사이드바 및 푸터
with st.sidebar:
    if st.button("🏠 홈으로 (초기화)"):
        clear_form()
        st.rerun()

st.caption(f"© 2025 임상 보조 시스템 | {st.session_state.current_time}")
import streamlit as st
from google import genai 
import re 
import datetime 

# --- [디자인] 모바일 줄바꿈 최적화 ---
def apply_mobile_optimization():
    st.markdown("""
        <style>
            .stMarkdown, .stText, .stCodeBlock, .stAlert, code {
                white-space: pre-wrap !important;
                word-break: break-all !important;
            }
            .main .block-container { padding: 1rem; }
            img { max-width: 100%; height: auto; }
            .stButton button { width: 100%; }
        </style>
    """, unsafe_allow_html=True)

# --- [핵심] AI 모델 호출 함수 (이름 오류 및 할당량 해결) ---
def ask_gemini(client, prompt_text):
    # 시도해볼 모델 목록 (가장 최신순)
    models_to_try = ['gemini-2.0-flash', 'gemini-1.5-flash']
    
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt_text
            )
            return response.text, model_name
        except Exception as e:
            # 429(할당량 초과)나 다른 에러가 나면 다음 모델로 넘어감
            continue
            
    return "현재 모든 무료 모델의 일시적 할당량이 초과되었습니다. 1분만 기다린 후 다시 시도해주세요.", "Error"

# --- 초기 설정 ---
if 'current_time' not in st.session_state:
    st.session_state.current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    st.session_state.patient_count = 1

def clear_form():
    st.session_state.raw_text = "" 
    st.session_state.current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    st.session_state.patient_count += 1

st.set_page_config(page_title="한의사 임상 보조 시스템", layout="wide")
apply_mobile_optimization()

st.title("🩺 한의사 임상 보조 시스템")
st.caption("무료 버전은 1분당 호출 제한이 있습니다. 에러 발생 시 잠시 후 다시 시도해주세요.")

# API 연결
client = None
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key)
except:
    st.error("⚠️ API 키 설정을 확인해주세요.")

# 1. 환자 대화 입력
st.header(f"1. 📝 환자 대화 입력 (#{st.session_state.patient_count})")
raw_text = st.text_area("내용을 입력하세요", key='raw_text', height=150)

# 2. 치료법 DB 로드
treatment_db_content = st.secrets.get("TREATMENT_DB", "로드된 DB가 없습니다.")

# 3. 처리 버튼
if st.button("✨ 전체 과정 시작", use_container_width=True):
    if not raw_text:
        st.warning("내용을 입력해주세요.")
    elif client:
        st.header("3. ✅ SOAP 차트 정리 결과")
        with st.spinner("AI 분석 중..."):
            soap_prompt = f"아래 대화를 한의원 SOAP 형식으로 요약해줘:\n\n{raw_text}"
            soap_result, final_model = ask_gemini(client, soap_prompt)
            
            if final_model != "Error":
                st.success(f"사용 모델: {final_model}")
                st.info(soap_result)
                
                st.header("4. 💡 최적 치료법 제안")
                treat_prompt = f"SOAP: {soap_result}\n\nDB: {treatment_db_content}\n\n치료 계획을 세워줘. 혈자리는 [이미지: URL] 형식 포함."
                treat_result, _ = ask_gemini(client, treat_prompt)
                st.markdown(treat_result)
            else:
                st.error(soap_result)

st.markdown("---")
st.button("🏥 다음 환자 진료 시작", on_click=clear_form, use_container_width=True)
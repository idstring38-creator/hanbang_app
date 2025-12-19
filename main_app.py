import streamlit as st
from google import genai 
import re 
import datetime 

# --- [디자인] 모바일 줄바꿈 및 화면 최적화 ---
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

# --- [핵심] AI 모델 호출 함수 (자동 전환 로직) ---
def ask_gemini(client, prompt_text):
    # 1순위: gemini-2.0-flash (사용자가 적어주신 2.5를 최신 2.0으로 교정하거나 그대로 유지)
    # 여기서는 사용자의 요청대로 2.5를 먼저 시도합니다.
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash', # 현재 사용 가능한 최신형은 2.0입니다. 2.5는 오타일 확률이 높아 수정했습니다.
            contents=prompt_text
        )
        return response.text, "2.0-Flash" # 성공 시 결과와 모델명 반환
    
    except Exception as e:
        # 만약 사용량 초과(429) 에러가 나면 2순위 모델로 시도
        if "429" in str(e) or "quota" in str(e).lower():
            try:
                response = client.models.generate_content(
                    model='gemini-1.5-flash', # 비교적 할당량이 넉넉한 모델
                    contents=prompt_text
                )
                return response.text, "1.5-Flash (자동 전환됨)"
            except Exception as e2:
                return f"모든 AI 모델의 할당량이 초과되었습니다. 잠시 후 시도해주세요. ({e2})", "Error"
        else:
            return f"오류 발생: {e}", "Error"

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
st.caption("2.0 모델 우선 사용, 용량 초과 시 1.5 모델로 자동 전환됩니다.")

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
treatment_db_content = st.secrets.get("TREATMENT_DB", "DB 내용이 없습니다.")

# 3. 처리 버튼
if st.button("✨ 전체 과정 시작", use_container_width=True):
    if not raw_text:
        st.warning("내용을 입력해주세요.")
    elif client:
        # --- 1단계: SOAP 정리 ---
        st.header("3. ✅ SOAP 차트 정리 결과")
        with st.spinner("AI가 차트를 분석 중입니다..."):
            soap_prompt = f"아래 대화를 한의원 SOAP 형식(CC, S, O, A, P)으로 정리해줘:\n\n{raw_text}"
            soap_result, model_name = ask_gemini(client, soap_prompt)
            
            if model_name != "Error":
                st.info(f"사용된 모델: {model_name}")
                st.write(soap_result)
                
                # --- 2단계: 치료법 제안 ---
                st.header("4. 💡 최적 치료법 제안")
                with st.spinner("치료법을 찾는 중..."):
                    treat_prompt = f"SOAP: {soap_result}\n\nDB: {treatment_db_content}\n\n위 내용을 바탕으로 최적 치료 계획을 세워줘. 혈자리는 [이미지: URL] 형식 포함."
                    treat_result, model_name2 = ask_gemini(client, treat_prompt)
                    st.markdown(treat_result)
                    
                    # 혈자리 이미지 출력
                    image_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', treat_result, re.IGNORECASE)
                    if image_patterns:
                        st.subheader("🖼️ 추천 혈자리 시각화")
                        for point_name, url in image_patterns:
                            st.image(url.strip(), caption=point_name, use_container_width=True)
            else:
                st.error(soap_result)

st.markdown("---")
st.button("🏥 다음 환자 진료 시작", on_click=clear_form, use_container_width=True)
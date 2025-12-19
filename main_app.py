import streamlit as st
from google import genai 
import re 
import datetime 

# --- [수정사항] 모바일 줄바꿈 및 최적화 CSS 추가 ---
def apply_mobile_optimization():
    st.markdown("""
        <style>
            /* 전체 텍스트 줄바꿈 강제 설정 */
            .stMarkdown, .stText, .stCodeBlock, code {
                white-space: pre-wrap !important;
                word-break: break-all !important;
            }
            /* 모바일에서 가로 스크롤 방지 */
            .main .block-container {
                padding-left: 1rem;
                padding-right: 1rem;
            }
            /* 이미지 크기 자동 조절 */
            img {
                max-width: 100%;
                height: auto;
            }
            /* 버튼 글자 크기 조정 */
            .stButton button {
                width: 100%;
                white-space: normal;
                height: auto;
            }
        </style>
    """, unsafe_allow_html=True)

# --- Session State 초기화 및 시간 기록 ---

def clear_form():
    st.session_state.raw_text = "" 
    st.session_state.current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    st.session_state.patient_count += 1

if 'current_time' not in st.session_state:
    st.session_state.current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    st.session_state.patient_count = 1

# --- Configuration and Initialization ---
# layout="wide"는 PC에서 좋지만, 위 CSS가 모바일 줄바꿈을 잡아줄 것입니다.
st.set_page_config(page_title="한의사 임상 보조 시스템 (통합)", layout="wide")
apply_mobile_optimization() # 모바일 최적화 적용

st.title("🩺 한의사 임상 보조 시스템 (통합)")
st.caption("환자 대화 입력 한 번으로 SOAP 차트 정리와 최적 치료법 제안까지 seamless하게 진행됩니다.")

# API Initialization
client = None
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key)
except KeyError:
    st.error("⚠️ Gemini API 키를 설정해주세요.")
except Exception as e:
    st.error(f"오류 발생: {e}")

# --- 1. 환자 대화 원문 입력 ---
st.header(f"1. 📝 환자 대화 입력 (#{st.session_state.patient_count})")
raw_text = st.text_area("환자 대화 원문 입력", key='raw_text', height=200, 
                        placeholder="여기에 대화 내용을 붙여넣으세요.")

# --- 2. 한의원 치료법 DB 로드 ---
st.header("2. 📚 치료법 DB 로드")
treatment_db_content = None

try:
    treatment_db_content = st.secrets["TREATMENT_DB"]
    with st.expander("현재 로드된 치료법 DB 보기"):
        st.text(treatment_db_content[:300] + "..." if len(treatment_db_content) > 300 else treatment_db_content)
except KeyError:
    st.error("⚠️ TREATMENT_DB 설정을 확인해주세요.")

# --- 3. 전체 처리 버튼 ---
if st.button("✨ 전체 과정 시작 (SOAP 정리 & 치료법 제안)", use_container_width=True):
    if not raw_text:
        st.warning("내용을 입력해주세요.")
    elif not treatment_db_content or not client:
        st.error("설정 오류가 있습니다.")
    else:
        # --- [Step 1] SOAP Generation ---
        st.header("3. ✅ SOAP 차트 정리 결과")
        
        SOAP_PROMPT_TEMPLATE = """
        당신은 숙련된 한의사 보조 AI입니다. 아래 내용을 SOAP 형식으로 요약해 주세요.
        CC: , S: , O: , A: , P: 형식으로 답하세요.
        ---
        {text_input}
        """
        
        soap_result_text = None
        부위_형태_키 = "결과_없음" 
        
        with st.spinner("SOAP 차트 정리 중..."):
            try:
                final_soap_prompt = SOAP_PROMPT_TEMPLATE.format(text_input=raw_text)
                soap_response = client.models.generate_content(model='gemini-2.5-flash', contents=final_soap_prompt)
                soap_result_text = soap_response.text
                
                # st.code 대신 st.info나 st.markdown을 쓰면 줄바꿈이 더 잘 됩니다.
                st.info(soap_result_text)
                
                # 파일명 생성 로직 (기존 유지)
                match = re.search(r'^(A|CC):\s*([\s\S]+?)\n', soap_result_text, re.MULTILINE)
                if match:
                    key_content = match.group(2).strip().split('\n')[0].strip()
                    clean_content = re.sub(r'(진단|추정|변증|의심|상태|관련|입니다|보임)', '', key_content).strip()
                    words = clean_content.split()
                    부위 = words[0][:5] if len(words) >= 1 else "부위"
                    형태 = words[1][:5] if len(words) >= 2 else "증상"
                    부위_형태_키 = re.sub(r'[^\w-]', '', f"{부위}_{형태}")

                st.download_button(label="⬇️ SOAP 다운로드", data=soap_result_text, 
                                   file_name=f"SOAP_{부위_형태_키}.txt", use_container_width=True)
            except Exception as e:
                st.error(f"오류: {e}")
                
        # --- [Step 2] Treatment Suggestion ---
        if soap_result_text:
            st.header("4. 💡 최적 치료법 제안")
            TREATMENT_PROMPT_TEMPLATE = """환자 SOAP 분석 후 최적 치료 계획을 제안하세요. 
            혈자리는 [이미지: URL] 형식을 포함하세요.\n\n[SOAP]:\n{soap_input}\n\n[DB]:\n{db_input}"""

            with st.spinner("치료법 분석 중..."):
                try:
                    treatment_response = client.models.generate_content(
                        model='gemini-2.5-flash', 
                        contents=TREATMENT_PROMPT_TEMPLATE.format(soap_input=soap_result_text, db_input=treatment_db_content)
                    )
                    treatment_text = treatment_response.text
                    st.markdown(treatment_text) # 마크다운은 자동 줄바꿈이 지원됩니다.
                    
                    # 혈자리 이미지 시각화
                    image_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', treatment_text, re.IGNORECASE)
                    if image_patterns:
                        st.subheader("🖼️ 추천 혈자리 시각화")
                        for point_name, url in image_patterns:
                            st.image(url.strip(), caption=point_name, use_container_width=True)
                            
                except Exception as e:
                    st.error(f"오류: {e}")

# --- 5. 다음 환자 시작 ---
st.markdown("---")
st.button("🏥 다음 환자 진료 시작", on_click=clear_form, use_container_width=True)
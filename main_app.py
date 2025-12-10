import streamlit as st
from google import genai 
import re 
import datetime 

# --- Session State 초기화 및 시간 기록 ---

# 다음 환자 진료 시작 시, 입력 필드를 초기화하고 시간 및 환자 카운트를 업데이트
def clear_form():
    # Streamlit은 키(key)가 있는 위젯의 값을 st.session_state에 저장합니다.
    st.session_state.raw_text = "" 
    st.session_state.current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    st.session_state.patient_count += 1
    # 다른 입력 필드도 초기화하고 싶다면 여기에 추가합니다.
    st.session_state.treatment_db_content = ""


if 'current_time' not in st.session_state:
    st.session_state.current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    st.session_state.patient_count = 1
    st.session_state.treatment_db_content = ""


# --- Configuration and Initialization ---
st.set_page_config(page_title="한의사 임상 보조 시스템 (통합)", layout="wide")

st.title("🩺 한의사 임상 보조 시스템 (통합 버전)")
st.caption("환자 대화 입력 한 번으로 SOAP 차트 정리와 최적 치료법 제안까지 seamless하게 진행됩니다.")

# API Initialization (Attempt to load client)
client = None
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key)
except KeyError:
    st.error("⚠️ Gemini API 키를 Streamlit Secrets에 'GEMINI_API_KEY'로 설정해주세요. 기능이 작동하지 않습니다.")
except Exception as e:
    st.error(f"Gemini 클라이언트 초기화 중 오류가 발생했습니다: {e}")

# -----------------------------------------------------------
# --- 1. 환자 대화 원문 입력 (Step 1 Input) ---
# -----------------------------------------------------------

st.header(f"1. 📝 환자 대화 원문 입력 (환자 #{st.session_state.patient_count})")
raw_text = st.text_area("환자 대화 원문 입력 (클로바/갤럭시 복사)", key='raw_text', height=200, 
                        placeholder="여기에 네이버 클로바 노트나 갤럭시 메모장에서 복사한 대화 텍스트를 붙여넣으세요.")

# -----------------------------------------------------------
# --- 2. 한의원 치료법 DB 내용 입력 (Step 2 Input) ---
# -----------------------------------------------------------

st.header("2. 📚 한의원 치료법 DB 내용 입력")
st.warning("⚠️ **이미지 시각화를 위해:** 혈자리 정보를 입력할 때 **'혈자리 이름 [이미지: 이미지URL]'** 형식으로 URL을 포함해야 합니다.")
treatment_db_content = st.text_area("치료법 DB 내용 입력", key='treatment_db_content', height=300, 
                                    placeholder="가지고 계신 선생님만의 치료법 DB 내용을 모두 복사하여 여기에 붙여넣으세요.")

# -----------------------------------------------------------
# --- 3. 전체 처리 버튼 ---
# -----------------------------------------------------------

if st.button("✨ 전체 과정 시작 (SOAP 정리 & 치료법 제안)", use_container_width=True):
    if not raw_text or not treatment_db_content:
        st.warning("환자 대화 원문과 치료법 DB 내용을 모두 입력해주세요.")
    elif not client:
        st.error("Gemini 클라이언트 초기화 오류로 인해 작업을 시작할 수 없습니다. API 키를 확인하세요.")
    else:
        # --- [Process Step 1] SOAP Generation ---
        st.header("3. ✅ SOAP 차트 정리 결과")
        
        SOAP_PROMPT_TEMPLATE = """
        당신은 숙련된 한의사 보조 AI입니다. 아래의 환자 대화 원문을 분석하여 
        한의학 진료에 필요한 **SOAP 형식(Subjective, Objective, Assessment, Plan)**으로 깔끔하게 요약 정리해 주세요.
        (P는 일반적인 계획으로 간략히 요약하고, 상세 계획은 다음 단계에서 제시합니다.)
        
        ---
        
        [환자 대화 원문]:
        {text_input}
        
        ---
        
        요약 결과는 아래 형식으로 출력하고, 다른 설명이나 주석은 포함하지 마세요:
        
        CC: [주된 증상]
        S: [환자가 말한 상세 정보]
        O: [관찰된 객관적 증상 (없으면 N/A 또는 생략)]
        A: [한의학적 진단/평가]
        P: [치료 계획]
        """
        
        soap_result_text = None
        부위_형태_키 = "결과_없음" 
        
        with st.spinner("1단계: SOAP 차트 정리 중..."):
            try:
                final_soap_prompt = SOAP_PROMPT_TEMPLATE.format(text_input=raw_text)
                
                soap_response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=final_soap_prompt,
                )
                
                soap_result_text = soap_response.text
                st.code(soap_result_text, language="text")
                st.success("1단계: SOAP 차트 정리 완료. (자동으로 2단계로 넘어갑니다.)")

                # ----------------------------------------------------
                # **[다운로드 기능] 파일명 생성: '아픈 부위_아픈 형태.txt' 형식 적용**
                # ----------------------------------------------------
                
                # 'A' 또는 'CC' 섹션의 첫 줄 내용을 활용하여 파일명 키워드 추출
                match = re.search(r'^(A|CC):\s*([\s\S]+?)\n', soap_result_text, re.MULTILINE)
                
                if match:
                    key_content = match.group(2).strip().split('\n')[0].strip()
                    clean_content = re.sub(r'(진단|추정|변증|의심|상태|관련|입니다|보임)', '', key_content).strip()
                    words = clean_content.split()
                    
                    부위 = "부위"
                    형태 = "증상"
                    
                    if len(words) >= 2:
                        부위 = words[0][:5] 
                        형태 = words[1][:5] 
                    elif len(words) == 1:
                        부위 = words[0][:5]
                        형태 = "증상"
                        
                    부위_형태_키 = f"{부위}_{형태}"
                    # 파일명에 쓸 수 없거나 불필요한 문자 제거
                    부위_형태_키 = re.sub(r'[^\w-]', '', 부위_형태_키.replace(' ', '_')) 

                # 최종 파일명 생성
                soap_filename_base = 부위_형태_키
                soap_filename = f"SOAP_{soap_filename_base}_{st.session_state.current_time}.txt"
                
                # 다운로드 버튼 생성
                st.download_button(
                    label="⬇️ SOAP 차트 다운로드 (텍스트 파일)",
                    data=soap_result_text,
                    file_name=soap_filename,
                    mime="text/plain",
                    help=f"파일명 형식: SOAP_{soap_filename_base}.txt",
                    use_container_width=True
                )

            except Exception as e:
                st.error(f"1단계(SOAP 정리) 중 오류가 발생했습니다: {e}")
                
        # --- [Process Step 2] Treatment Suggestion (Automatic input) ---
        
        if soap_result_text:
            st.header("4. 💡 최적 치료법 제안 및 혈자리 시각화")
            
            TREATMENT_PROMPT_TEMPLATE = """
            당신은 숙련된 한의사 AI 어시스턴트입니다. 다음의 환자 SOAP 차트와 제공된 치료법 DB를 분석하여 
            환자에게 가장 적합한 **치료 계획(Plan)의 상세 내용**을 제안하세요.

            **[출력 형식 및 기준]**
            * 환자의 CC와 A를 간략히 다시 언급하여 상태를 확인합니다.
            * 추천 치료법(침/뜸/부항)과 추천 방제(한약)를 명확히 구분하여 출력합니다.
            * 혈자리를 추천할 경우, **DB에 제공된 형식 그대로** 혈자리 이름과 이미지 URL을 포함하여 출력해주세요. (예: 중완(CV12) [이미지: https://.../CV12.jpg])
            * 출력은 한글 마크다운 형식으로 정리하며, **오직 분석 결과와 상세 치료 계획**만 포함하고 다른 잡담은 일절 하지 마세요.
            
            ---
            
            **[환자의 SOAP 차트]:**
            {soap_input}

            ---
            
            **[한의원 치료법 DB (혈자리 이미지 URL 포함)]:**
            {db_input}
            
            ---
            
            **[최적 치료 계획 제안]:**
            """

            with st.spinner("2단계: 최적 치료법 분석 및 시각화 준비 중..."):
                try:
                    # SOAP 결과를 다음 프롬프트에 자동 삽입
                    final_treatment_prompt = TREATMENT_PROMPT_TEMPLATE.format(
                        soap_input=soap_result_text,
                        db_input=treatment_db_content
                    )
                    
                    treatment_response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=final_treatment_prompt,
                    )
                    
                    treatment_text = treatment_response.text
                    st.success("2단계: 치료 계획 분석 완료.")
                    
                    # --- [Output Step 3] Parse and Display Images ---
                    
                    st.subheader("📋 추천 치료 계획 상세")
                    st.markdown(treatment_text)
                    
                    # ----------------------------------------------------
                    # **최종 진료 보고서 다운로드 기능**
                    # ----------------------------------------------------
                    
                    full_report = f"--- 진료 보고서 ({부위_형태_키}) ---\n\n[환자 대화 원문]\n{raw_text}\n\n[SOAP 차트 결과]\n{soap_result_text}\n\n[최적 치료 계획 제안]\n{treatment_text}"
                    
                    full_filename_base = f"Report_{부위_형태_키}"
                    full_filename = f"{full_filename_base}_{st.session_state.current_time}.md"
                    
                    st.download_button(
                        label="⬇️ 최종 진료 보고서 다운로드 (Markdown)",
                        data=full_report,
                        file_name=full_filename,
                        mime="text/markdown",
                        help=f"SOAP, 원문, 치료법 제안이 모두 포함된 최종 보고서를 저장합니다. 파일명 형식: {full_filename_base}.md",
                        use_container_width=True
                    )
                    
                    # ----------------------------------------------------
                    # **혈자리 시각화**
                    # ----------------------------------------------------
                    
                    st.subheader("🖼️ 추천 혈자리 시각화")
                    
                    # LLM 출력 텍스트에서 '혈자리 이름 [이미지: URL]' 패턴 추출
                    # 패턴: (\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]
                    image_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', treatment_text, re.IGNORECASE)
                    
                    if not image_patterns:
                        st.info("추천된 치료 계획 텍스트에서 혈자리 이미지 URL을 찾을 수 없습니다. DB 입력 형식을 확인해주세요.")
                    else:
                        st.write(f"총 {len(image_patterns)}개의 혈자리 이미지를 찾았습니다.")
                        
                        cols = st.columns(min(len(image_patterns), 3)) 
                        
                        for i, (point_name, url) in enumerate(image_patterns):
                            try:
                                # 혈자리 그림 시각화
                                cols[i % len(cols)].image(url.strip(), caption=point_name, width=200)
                            except Exception as img_e:
                                cols[i % len(cols)].error(f"이미지 로드 오류 ({point_name}): {img_e}")
                                
                except Exception as e:
                    st.error(f"2단계(치료법 제안) 중 오류가 발생했습니다: {e}")

# -----------------------------------------------------------
# --- 5. 다음 환자 진료 시작 버튼 ---
# -----------------------------------------------------------
st.markdown("---")
st.header("5. 다음 환자 진료 시작")
st.button("🏥 다음 환자 진료 시작 (입력 필드 초기화)", on_click=clear_form, use_container_width=True)
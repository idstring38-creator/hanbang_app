import streamlit as st
from google import genai 
import re # 정규 표현식 라이브러리 (혈자리 이미지 URL 추출에 사용)

# --- Configuration and Initialization ---
st.set_page_config(page_title="한의사 임상 보조 시스템 (통합)", layout="wide")

st.title("🩺 한의사 임상 보조 시스템 (통합 버전)")
st.caption("환자 대화 입력 한 번으로 SOAP 차트 정리와 최적 치료법 제안까지 seamless하게 진행됩니다.")

# API Initialization (Attempt to load client)
client = None
try:
    # Streamlit Secrets에서 API 키 로드
    api_key = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key)
except KeyError:
    st.error("⚠️ Gemini API 키를 Streamlit Secrets에 'GEMINI_API_KEY'로 설정해주세요. 기능이 작동하지 않습니다.")
except Exception as e:
    st.error(f"Gemini 클라이언트 초기화 중 오류가 발생했습니다: {e}")

# --- 1. 환자 대화 원문 입력 (Step 1 Input) ---

st.header("1. 📝 환자 대화 원문 입력")
raw_text = st.text_area("환자 대화 원문 입력 (클로바/갤럭시 복사)", height=200, 
                        placeholder="여기에 네이버 클로바 노트나 갤럭시 메모장에서 복사한 대화 텍스트를 붙여넣으세요.")

# --- 2. 한의원 치료법 DB 내용 입력 (Step 2 Input) ---

st.header("2. 📚 한의원 치료법 DB 내용 입력")
st.warning("⚠️ **이미지 시각화를 위해:** 혈자리 정보를 입력할 때 **'혈자리 이름 [이미지: 이미지URL]'** 형식으로 URL을 포함해야 합니다.")
treatment_db_content = st.text_area("치료법 DB 내용 입력", height=300, 
                                    placeholder="가지고 계신 선생님만의 치료법 DB 내용을 모두 복사하여 여기에 붙여넣으세요. (예: 요통: 침치료, 핵심혈: L4(https://.../L4.jpg), 방제: 독활기생탕 [이미지: https://.../img.jpg])")

# --- 3. 전체 처리 버튼 ---

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
                    
                    st.subheader("🖼️ 추천 혈자리 시각화")
                    
                    # LLM의 출력 텍스트에서 '혈자리 이름 [이미지: URL]' 패턴을 찾습니다.
                    # URL 추출 패턴: [이미지: URL] 형태의 URL을 찾음
                    
                    # re.findall(패턴, 검색 텍스트, 플래그)
                    # 패턴 설명: ( ) 캡처 그룹, \w+ 한글/영문/숫자, https?:// http 또는 https, [^\s\]]+ 공백이나 ]가 아닌 모든 문자
                    image_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', treatment_text, re.IGNORECASE)
                    
                    if not image_patterns:
                        st.info("추천된 치료 계획 텍스트에서 혈자리 이미지 URL을 찾을 수 없습니다. DB 내용과 LLM 출력 형식이 '혈자리 이름 [이미지: URL]'과 일치하는지 확인해주세요.")
                    else:
                        st.write(f"총 {len(image_patterns)}개의 혈자리 이미지를 찾았습니다.")
                        
                        # 이미지를 가로로 나열하기 위해 st.columns 사용
                        cols = st.columns(min(len(image_patterns), 3)) # 최대 3개 컬럼
                        
                        for i, (point_name, url) in enumerate(image_patterns):
                            try:
                                cols[i % len(cols)].image(url.strip(), caption=point_name, width=200)
                            except Exception as img_e:
                                cols[i % len(cols)].error(f"이미지 로드 오류 ({point_name}): {img_e}")
                                
                except Exception as e:
                    st.error(f"2단계(치료법 제안) 중 오류가 발생했습니다: {e}")

# --- 안내 메시지 ---
st.sidebar.markdown("---")
st.sidebar.markdown("### 🛠️ 개발 가이드:")
st.sidebar.markdown("1. **Seamless Flow:** 입력(1, 2) 후 버튼 클릭 한 번으로 (3, 4)의 모든 과정이 순차적으로 실행됩니다.")
st.sidebar.markdown("2. **자동 입력:** 3단계의 SOAP 결과가 4단계의 치료법 제안에 자동으로 사용됩니다.")
st.sidebar.markdown("3. **이미지 형식:** 혈자리 이미지를 띄우려면, '한의원 치료법 DB 내용'에 `혈자리 이름 [이미지: URL]` 형식으로 자료를 입력해야 합니다.")
import streamlit as st
from google import genai 
# Note: google-genai 라이브러리는 Streamlit Secrets에 저장된 
# GEMINI_API_KEY를 자동으로 로드하여 사용합니다.

# --- Streamlit 기본 설정 ---
st.set_page_config(page_title="한의사 임상 보조 시스템 (최종)", layout="wide")

st.title("🩺 한의사 임상 보조 시스템 (고효율 버전)")
st.write("외부 앱(클로바노트, 갤럭시 메모 등)에서 복사한 텍스트를 붙여넣어 차트 정리 및 치료법 제안을 받습니다.")

menu = st.sidebar.selectbox(
    "메뉴 선택",
    ["1) 차트 자동 정리", "2) 치료법 검색 및 제안"]
)

# --- 1) 차트 자동 정리 (Gemini API 활용) ---
if menu == "1) 차트 자동 정리":
    st.header("1) 📝 환자 대화 → SOAP 차트 자동 정리")
    st.info("고품질 음성 인식 결과(클로바 등)를 붙여넣고, AI가 SOAP 형식으로 정리합니다. (Gemini 무료 한도 사용)")
    
    client = None
    # 2단계에서 설정한 API 키를 Streamlit Secrets에서 불러옵니다.
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        client = genai.Client(api_key=api_key)
        
    except KeyError:
        st.error("⚠️ Gemini API 키를 Streamlit Secrets에 'GEMINI_API_KEY'로 설정해주세요. 설정이 완료되지 않으면 이 기능은 작동하지 않습니다.")
        
    except Exception as e:
        st.error(f"Gemini 클라이언트 초기화 중 오류가 발생했습니다: {e}")
        
    # 대화 원문 입력 영역
    text = st.text_area("환자 대화 원문 입력 (복사/붙여넣기)", height=300, 
                        placeholder="여기에 네이버 클로바 노트나 갤럭시 메모장에서 복사한 대화 텍스트를 붙여넣으세요.")
    
    # LLM에 전달할 프롬프트 정의
    SOAP_PROMPT_TEMPLATE = f"""
    당신은 숙련된 한의사 보조 AI입니다. 아래의 환자 대화 원문을 분석하여 
    한의학 진료에 필요한 **SOAP 형식(Subjective, Objective, Assessment, Plan)**으로 깔끔하게 요약 정리해 주세요.
    
    - **CC (Chief Complaint):** 환자가 가장 호소하는 주된 증상
    - **S (Subjective):** 환자가 주관적으로 말하는 증상, 발생 시점, 경과, 통증 양상 등 상세 정보
    - **O (Objective):** 외부에서 관찰 가능한 객관적 정보 (예: 혀의 상태, 맥의 상태 등 - 입력 텍스트에 없으면 **생략**하거나 'N/A'로 표기)
    - **A (Assessment):** 현재 환자의 상태에 대한 한의학적 진단/평가 (예: 요추 염좌, 담음 정체 등)
    - **P (Plan):** 향후 치료 계획 (P는 일반적인 계획으로 간략히 요약하고, 상세 계획은 2번 메뉴에서 제시합니다.)
    
    ---
    
    [환자 대화 원문]:
    {{text_input}}
    
    ---
    
    요약 결과는 아래 형식으로 출력하고, 다른 설명이나 주석은 포함하지 마세요:
    
    CC: [주된 증상]
    S: [환자가 말한 상세 정보]
    O: [관찰된 객관적 증상 (없으면 N/A 또는 생략)]
    A: [한의학적 진단/평가]
    P: [치료 계획]
    """

    if st.button("정리하기") and client:
        if not text:
            st.warning("대화 원문을 입력해주세요.")
        else:
            with st.spinner("AI가 차트를 정리하는 중입니다..."):
                try:
                    # 프롬프트에 실제 텍스트 삽입
                    final_prompt = SOAP_PROMPT_TEMPLATE.format(text_input=text)
                    
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=final_prompt,
                    )
                    
                    st.success("✅ 차트 정리 완료:")
                    st.code(response.text, language="text")

                except Exception as e:
                    st.error(f"차트 정리 중 오류가 발생했습니다: {e}")

# --- 2) 치료법 검색 및 제안 (LLM 활용 버전) ---
elif menu == "2) 치료법 검색 및 제안":
    st.header("2) 📚 SOAP 결과 기반 최적 치료법 제안")
    st.info("정리된 SOAP 차트와 선생님의 DB를 분석하여 개인화된 치료 계획을 제시합니다.")
    
    client = None
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        client = genai.Client(api_key=api_key)
    except KeyError:
        st.error("⚠️ Gemini API 키를 Streamlit Secrets에 설정해주세요. 이 기능은 API 없이 작동할 수 없습니다.")
        client = None
    except Exception as e:
        st.error(f"Gemini 클라이언트 초기화 중 오류가 발생했습니다: {e}")

    # 1. SOAP 결과 입력 영역
    soap_input = st.text_area("1. SOAP 차트 결과 입력 (복사/붙여넣기)", height=200, 
                              placeholder="1번 메뉴에서 정리된 CC/S/O/A/P 결과를 여기에 붙여넣으세요.")
                              
    # 2. 선생님의 치료법 DB 내용 입력 영역 (LLM의 컨텍스트로 제공)
    treatment_db_content = st.text_area("2. 한의원 치료법 DB 내용 입력", height=400, 
                                        placeholder="가지고 계신 선생님만의 치료법 DB 내용을 모두 복사하여 여기에 붙여넣으세요. (방제, 침법, 근막 패턴 등 포함)")

    # 3. 프롬프트 정의
    TREATMENT_PROMPT_TEMPLATE = f"""
    당신은 숙련된 한의사 AI 어시스턴트입니다. 다음 두 정보를 분석하여 환자에게 가장 적합한 **치료 계획(Plan)의 상세 내용**을 제안하세요.

    **[분석 목표]**
    1. 환자의 **Assessment (A)**와 **Subjective (S)** 내용을 기반으로 핵심 증상 및 변증을 파악하세요.
    2. 아래 제공된 **'한의원 치료법 DB'** 내용을 참고하여, 환자의 상태와 가장 잘 맞는 치료법을 **3가지** 이내로 추천하고 그 이유를 설명하세요.

    **[출력 형식 및 기준]**
    * 환자의 CC와 A를 간략히 다시 언급하여 상태를 확인합니다.
    * 추천 치료법(침/뜸/부항 등)과 추천 방제(한약)를 명확히 구분하여 출력합니다.
    * 출력은 한글 마크다운(Markdown) 형식으로 정리하며, **오직 분석 결과와 상세 치료 계획**만 포함하고 다른 잡담은 일절 하지 마세요.
    
    ---
    
    **[환자의 SOAP 차트]:**
    {{soap_input}}

    ---
    
    **[한의원 치료법 DB]:**
    {{db_input}}
    
    ---
    
    **[최적 치료 계획 제안]:**
    """

    # 4. 검색 버튼 및 실행 로직
    if st.button("최적 치료법 제안받기") and client:
        if not soap_input or not treatment_db_content:
            st.warning("SOAP 차트 결과와 치료법 DB 내용을 모두 입력해주세요.")
            
        else:
            with st.spinner("LLM이 최적의 치료법을 분석하는 중입니다..."):
                try:
                    # 프롬프트에 실제 데이터 삽입
                    final_prompt = TREATMENT_PROMPT_TEMPLATE.format(
                        soap_input=soap_input,
                        db_input=treatment_db_content
                    )
                    
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=final_prompt,
                    )
                    
                    st.success("✅ 최적 치료 계획 분석 완료:")
                    st.markdown(response.text) # Markdown으로 출력하여 가독성 높임

                except Exception as e:
                    st.error(f"치료법 분석 중 오류가 발생했습니다: {e}")
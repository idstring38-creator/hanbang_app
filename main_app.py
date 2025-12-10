import streamlit as st
from google import genai 
import os # API 키 로드를 위해 필요 (Streamlit Secrets에서 로드)

# --- Streamlit 기본 설정 ---
st.set_page_config(page_title="한의사 임상 보조 시스템", layout="wide")

st.title("🩺 한의사 임상 보조 시스템 (일원화 버전)")
st.write("외부 앱(클로바노트, 갤럭시 메모)에서 복사/붙여넣기를 통해 고품질의 텍스트를 입력받아 처리합니다.")

menu = st.sidebar.selectbox(
    "메뉴 선택",
    ["1) 차트 자동 정리", "2) 치료법 검색"]
)

# --- 1) 차트 자동 정리 (Gemini API 활용) ---
if menu == "1) 차트 자동 정리":
    st.header("1) 📝 환자 대화 → SOAP 차트 자동 정리")
    st.info("클로바/갤럭시 등에서 복사한 환자 대화 원문을 붙여넣고 정리하세요. (Gemini 무료 한도 사용)")
    
    client = None
    # 2단계에서 설정한 API 키를 Streamlit Secrets에서 불러옵니다.
    try:
        # st.secrets에서 GEMINI_API_KEY를 불러옵니다.
        # Streamlit Cloud 환경에서는 st.secrets["GEMINI_API_KEY"]로 불러옵니다.
        api_key = st.secrets["GEMINI_API_KEY"]
        client = genai.Client(api_key=api_key)
        
    except KeyError:
        # 키가 설정되지 않았을 경우 경고 메시지를 띄웁니다.
        st.error("⚠️ Gemini API 키를 Streamlit Secrets에 'GEMINI_API_KEY'로 설정해주세요. (이전 단계 참조)")
        
    except Exception as e:
        st.error(f"Gemini 클라이언트 초기화 중 오류가 발생했습니다: {e}")
        
    # 대화 원문 입력 영역
    text = st.text_area("환자 대화 원문 입력 (복사/붙여넣기)", height=300, 
                        placeholder="여기에 네이버 클로바 노트나 갤럭시 메모장에서 복사한 대화 텍스트를 붙여넣으세요.")
    
    # LLM에 전달할 프롬프트 정의
    prompt_template = f"""
    당신은 숙련된 한의사 보조 AI입니다. 아래의 환자 대화 원문을 분석하여 
    한의학 진료에 필요한 **SOAP 형식(Subjective, Objective, Assessment, Plan)**으로 깔끔하게 요약 정리해 주세요.
    
    - **CC (Chief Complaint):** 환자가 가장 호소하는 주된 증상
    - **S (Subjective):** 환자가 주관적으로 말하는 증상, 발생 시점, 경과, 통증 양상 등 상세 정보
    - **O (Objective):** 외부에서 관찰 가능한 객관적 정보 (예: 혀의 상태, 맥의 상태 등 - 입력 텍스트에 없으면 **생략**하거나 'N/A'로 표기)
    - **A (Assessment):** 현재 환자의 상태에 대한 한의학적 진단/평가 (예: 요추 염좌, 담음 정체 등)
    - **P (Plan):** 향후 치료 계획 (예: 침 치료, 부항, 한약 처방 등)
    
    ---
    
    [환자 대화 원문]:
    {text}
    
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
                    # Gemini 모델로 요청 보내기 (가장 빠르고 좋은 gemini-2.5-flash 사용)
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt_template,
                    )
                    
                    st.success("✅ 차트 정리 완료:")
                    st.code(response.text, language="text")

                except Exception as e:
                    st.error(f"차트 정리 중 오류가 발생했습니다: {e}")

# --- 2) 치료법 검색 (순수 Python 구현 예정) ---
elif menu == "2) 치료법 검색":
    st.header("2) 📚 SOAP 결과 기반 최적 치료법 검색")
    st.info("이 기능은 순수 Python 로직으로 DB(SQLite/CSV)를 검색하여 작동하며, 완전히 무료입니다.")
    st.warning("❗ 다음 단계에서 구현될 예정입니다.")
    
    # 이 부분에 '1) 차트 자동 정리' 메뉴에서 정리된 SOAP 결과가 자동으로 입력되도록 구현할 예정입니다.
    # 지금은 테스트용 입력창을 남겨둡니다.
    soap_input = st.text_area("SOAP 결과 붙여넣기", height=200, 
                              placeholder="1번 메뉴에서 정리된 SOAP 결과를 복사하여 여기에 붙여넣으세요.")
    
    keyword = st.text_input("추가 증상/키워드 입력 (선택 사항)")

    if st.button("최적 치료법 검색"):
        st.success("치료법 검색 로직이 아직 구현되지 않았습니다. 다음 단계에서 이 기능을 완성합니다.")
        st.write(f"SOAP 내용: {soap_input[:50]}...")
        st.write(f"키워드: {keyword}")
        
        # [여기에 SQLite/CSV 검색 및 매칭 로직이 들어갈 예정입니다.]
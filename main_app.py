import streamlit as st
from google import genai
import re
import datetime
import time
from groq import Groq

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

def clear_form():
    st.session_state.raw_text = ""
    st.session_state.current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    st.session_state.patient_count += 1
    st.session_state.step = "input"
    st.session_state.soap_result = ""
    st.session_state.follow_up_questions = ""
    st.session_state.additional_info = ""

# --- 2. 커스텀 CSS ---
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
        line-height: 1.5; /* 줄바꿈 간격 최적화 */
    }

    .stButton>button {
        width: 100%;
        border-radius: 16px;
        height: 4.5em;
        background-color: #2563eb;
        color: white !important;
        font-weight: 800;
        font-size: 1.25rem !important;
        border: none;
        box-shadow: 0 8px 15px rgba(37, 99, 235, 0.3);
    }
    
    .verify-btn>button {
        background-color: #059669 !important; /* 초록색 버튼으로 구분 */
        box-shadow: 0 8px 15px rgba(5, 150, 105, 0.3) !important;
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

# --- 3. API 클라이언트 ---
gemini_client = None
try:
    gemini_client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
except:
    st.error("⚠️ Gemini API 키를 확인해주세요.")

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

# --- 4. 분석 엔진 ---
def analyze_with_hybrid_fallback(prompt):
    gemini_models = ['models/gemini-1.5-flash', 'models/gemini-1.5-flash-8b']
    for model in gemini_models:
        try:
            response = gemini_client.models.generate_content(model=model, contents=prompt)
            return response.text
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                continue
            break
            
    if groq_client:
        try:
            chat_completion = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.3,
            )
            return chat_completion.choices[0].message.content
    
    raise Exception("API 연결 실패")

def clean_newlines(text):
    # 과도한 줄바꿈(3개 이상)을 2개로 줄임
    return re.sub(r'\n{3,}', '\n\n', text).strip()

# --- 5. UI 및 로직 ---
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
                    # 1차 분석 프롬프트 (SOAP + 추가 확인 사항)
                    FIRST_PROMPT = f"""
                    한의사 보조 AI로서 다음 대화 원문을 분석하세요.
                    1. SOAP 형식으로 요약 (줄바꿈 최소화).
                    2. 진단을 확정하기 위해 추가로 환자에게 물어봐야 할 질문이나 필요한 이학적 검사(SLR, ROM 등)가 있다면 [추가 확인 사항] 섹션에 리스트로 작성하세요. 없다면 '없음'이라고 적으세요.
                    
                    [대화]: {raw_text}
                    """
                    result = analyze_with_hybrid_fallback(FIRST_PROMPT)
                    
                    # 결과 파싱
                    if "[추가 확인 사항]" in result:
                        parts = result.split("[추가 확인 사항]")
                        st.session_state.soap_result = clean_newlines(parts[0])
                        st.session_state.follow_up_questions = clean_newlines(parts[1])
                    else:
                        st.session_state.soap_result = clean_newlines(result)
                        st.session_state.follow_up_questions = "없음"
                    
                    st.session_state.raw_text = raw_text
                    
                    # 추가 확인 사항이 '없음'이면 바로 결과 단계로, 있으면 검증 단계로
                    if "없음" in st.session_state.follow_up_questions or len(st.session_state.follow_up_questions) < 5:
                        st.session_state.step = "result"
                        st.rerun()
                    else:
                        st.session_state.step = "verify"
                        st.rerun()
            else:
                st.warning("내용을 입력해주세요.")
        st.markdown('</div>', unsafe_allow_html=True)

# [Step 2] 추가 문진 및 이학적 검사 확인
elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("📋 1차 SOAP 요약")
    st.markdown(f'<div class="soap-box">{st.session_state.soap_result}</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="q-box">', unsafe_allow_html=True)
    st.markdown("##### 🔍 추가 확인이 필요합니다")
    st.markdown(st.session_state.follow_up_questions)
    st.markdown('</div>', unsafe_allow_html=True)
    
    additional_info = st.text_area("추가 확인 내용 또는 검사 결과 입력", key="additional_info", placeholder="예: SLR 30도에서 양성, 야간통은 없음...")
    
    st.markdown('<div class="verify-btn">', unsafe_allow_html=True)
    if st.button("✅ 최종 확인 및 처방 생성"):
        st.session_state.additional_input = additional_info
        st.session_state.step = "result"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# [Step 3] 최종 결과 출력
elif st.session_state.step == "result":
    with st.spinner("최종 치료 계획을 수립 중..."):
        FINAL_PROMPT = f"""
        당신은 한의사 보조 AI입니다. 아래 정보를 바탕으로 육기(六氣) 원·락·극 체계에 맞춘 최종 치료 Plan을 작성하세요.
        
        [치료 DB]: {treatment_db_content}
        [1차 분석]: {st.session_state.soap_result}
        [추가 정보]: {getattr(st.session_state, 'additional_input', '없음')}
        
        **작성 가이드**:
        1. 추천 혈자리: '이름(코드) [이미지: URL]' 형식 유지.
        2. **선택 이유 (필수)**: 각 혈자리를 선택한 이유를 육기 이론과 환자 증상을 연결하여 상세히 설명하세요. 
           (예: "환자는 어제부터 당기는 근육통을 호소하는데 이 증상은 궐음풍목에 속하며, 어제 발생한 급성 증상이므로 락(Luo)에 해당합니다. 따라서 궐음락인 내관-여구를 선택하여 근육 압력을 해소합니다.")
        3. 요약된 SOAP 차트도 포함하세요.
        """
        final_result = analyze_with_hybrid_fallback(FINAL_PROMPT)
        
        st.markdown('<div class="stCard">', unsafe_allow_html=True)
        st.subheader("💡 최종 추천 치료 및 처방")
        st.markdown(final_result)
        
        # 이미지 렌더링
        img_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', final_result, re.I)
        if img_patterns:
            st.divider()
            st.markdown("##### 🖼️ 혈자리 위치 가이드")
            for name, url in img_patterns:
                st.image(url.strip(), caption=name, use_container_width=True)
        
        if st.button("🔄 진료 종료 및 초기화"):
            clear_form()
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

# 사이드바
with st.sidebar:
    st.title("진료 제어")
    if st.button("홈으로 (초기화)"):
        clear_form()
        st.rerun()

st.divider()
st.caption(f"© 2025 임상 보조 시스템 | {st.session_state.current_time}")
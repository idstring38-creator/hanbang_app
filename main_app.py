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
if 'raw_text' not in st.session_state:
    st.session_state.raw_text = ""
if 'additional_input' not in st.session_state:
    st.session_state.additional_input = ""

def clear_form():
    st.session_state.raw_text = ""
    st.session_state.current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    st.session_state.patient_count += 1
    st.session_state.step = "input"
    st.session_state.soap_result = ""
    st.session_state.follow_up_questions = ""
    st.session_state.additional_input = ""

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
        line-height: 1.5;
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
        background-color: #059669 !important;
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

# --- 4. 분석 엔진 ---
def analyze_with_hybrid_fallback(prompt):
    # 1단계: Gemini
    gemini_models = ['models/gemini-1.5-flash', 'models/gemini-1.5-flash-8b']
    for model in gemini_models:
        try:
            response = gemini_client.models.generate_content(model=model, contents=prompt)
            if response and response.text:
                return response.text
        except Exception as e:
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
                    FIRST_PROMPT = f"""
                    당신은 노련한 한의사 보조 AI입니다. 다음 대화 원문을 바탕으로 '문진 단계'를 수행하세요.
                    절대로 먼저 치료법이나 혈자리를 추천하지 마세요.
                    
                    **답변 형식**:
                    1. [SOAP 요약]: 환자의 주소증과 현 상태를 SOAP 형식으로 간략히 요약하세요 (줄바꿈 최소화).
                    2. [추가 확인 사항]: 정확한 육기 진단과 원락극 처방을 위해 원장님이 환자에게 추가로 물어봐야 할 질문이나 수행해야 할 이학적 검사 리스트를 작성하세요.
                    
                    [대화 원문]: {raw_text}
                    """
                    try:
                        result = analyze_with_hybrid_fallback(FIRST_PROMPT)
                        
                        # 섹션 구분 파싱
                        if "[추가 확인 사항]" in result:
                            parts = result.split("[추가 확인 사항]")
                            st.session_state.soap_result = clean_newlines(parts[0].replace("[SOAP 요약]", "").strip())
                            st.session_state.follow_up_questions = clean_newlines(parts[1].strip())
                        else:
                            st.session_state.soap_result = clean_newlines(result.replace("[SOAP 요약]", "").strip())
                            st.session_state.follow_up_questions = "추가 질문 없음"
                        
                        st.session_state.raw_text = raw_text
                        
                        # 무조건 verify 단계로 이동하여 원장님의 확인을 거치도록 함
                        st.session_state.step = "verify"
                        st.rerun()
                    except Exception as e:
                        st.error(f"분석 중 오류 발생: {e}")
            else:
                st.warning("내용을 입력해주세요.")
        st.markdown('</div>', unsafe_allow_html=True)

# [Step 2] 추가 문진 및 이학적 검사 확인
elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("📋 1차 SOAP 요약")
    st.markdown(f'<div class="soap-box">{st.session_state.soap_result}</div>', unsafe_allow_html=True)
    
    # 추가 질문이 있는 경우에만 질문 박스 표시
    if st.session_state.follow_up_questions and "질문 없음" not in st.session_state.follow_up_questions:
        st.markdown('<div class="q-box">', unsafe_allow_html=True)
        st.markdown("##### 🔍 추가 확인이 필요합니다")
        st.markdown(st.session_state.follow_up_questions)
        st.markdown('</div>', unsafe_allow_html=True)
    
    # 입력창 크기를 Step 1과 동일하게 height=200으로 설정
    additional_info = st.text_area(
        "추가 확인 내용 또는 검사 결과 입력 (선택사항)", 
        key="additional_info_input", 
        height=200,
        placeholder="예: 야간통 없음, SLR 70도 정상..."
    )
    
    st.markdown('<div class="verify-btn">', unsafe_allow_html=True)
    if st.button("✅ 최종 확인 및 처방 생성"):
        st.session_state.additional_input = additional_info if additional_info else "특이사항 없음"
        st.session_state.step = "result"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# [Step 3] 최종 결과 출력
elif st.session_state.step == "result":
    with st.spinner("최종 치료 계획을 수립 중..."):
        FINAL_PROMPT = f"""
        당신은 한의사 보조 AI입니다. 아래 정보를 종합하여 육기(六氣) 원·락·극 체계에 맞춘 최종 치료 Plan을 작성하세요.
        
        [치료 DB]: {treatment_db_content}
        [1차 SOAP 요약]: {st.session_state.soap_result}
        [추가 문진 정보]: {st.session_state.additional_input}
        
        **작성 가이드**:
        1. 추천 혈자리: '이름(코드) [이미지: URL]' 형식 유지.
        2. **선택 이유 (필수)**: 각 혈자리를 선택한 이유를 육기 이론(궐음, 소양 등)과 환자의 구체적 증상을 연결하여 상세히 설명하세요.
        3. 최종 완성된 SOAP 차트를 포함하세요.
        """
        try:
            final_result = analyze_with_hybrid_fallback(FINAL_PROMPT)
            
            st.markdown('<div class="stCard">', unsafe_allow_html=True)
            st.subheader("💡 최종 추천 치료 및 처방")
            st.markdown(final_result)
            
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
        except Exception as e:
            st.error(f"최종 분석 중 오류 발생: {e}")
            if st.button("처음으로 돌아가기"):
                clear_form()
                st.rerun()

# 사이드바
with st.sidebar:
    st.title("진료 제어")
    if st.button("홈으로 (초기화)"):
        clear_form()
        st.rerun()

st.divider()
st.caption(f"© 2025 임상 보조 시스템 | {st.session_state.current_time}")
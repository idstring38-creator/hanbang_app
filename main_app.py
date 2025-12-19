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
    layout="centered",  # 중앙 집중형 레이아웃으로 변경 (모바일 가독성 향상)
    initial_sidebar_state="collapsed"
)

# 세션 상태 초기화
if 'patient_count' not in st.session_state:
    st.session_state.patient_count = 1
if 'current_time' not in st.session_state:
    st.session_state.current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def clear_form():
    st.session_state.raw_text = ""
    st.session_state.current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    st.session_state.patient_count += 1

# --- 2. 커스텀 CSS (모바일 UI 및 모델 태그 강화) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Noto Sans KR', sans-serif;
        background-color: #f8fafc;
    }
    
    /* 카드형 컨테이너 */
    .stCard {
        background-color: #ffffff;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        border: 1px solid #e2e8f0;
        margin-bottom: 20px;
        position: relative;
    }
    
    /* 제목 및 텍스트 스타일 */
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
        line-height: 1.6;
    }

    /* 모바일용 더 큰 분석 버튼 */
    .stButton>button {
        width: 100%;
        border-radius: 16px;
        height: 4.5em; /* 버튼 크기 확대 */
        background-color: #2563eb;
        color: white !important;
        font-weight: 800;
        font-size: 1.25rem !important; /* 폰트 크기 확대 */
        border: none;
        box-shadow: 0 8px 15px rgba(37, 99, 235, 0.3);
        transition: all 0.2s;
    }
    
    .stButton>button:active {
        transform: scale(0.98);
        box-shadow: 0 4px 8px rgba(37, 99, 235, 0.2);
    }
    
    /* 모델 구분 태그 디자인 강화 */
    .model-info-tag {
        display: inline-block;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 20px;
        margin-bottom: 10px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .gemini-tag {
        background-color: #dbeafe;
        color: #1e40af;
        border: 1px solid #bfdbfe;
    }
    
    .groq-tag {
        background-color: #fef3c7;
        color: #92400e;
        border: 1px solid #fde68a;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. API 클라이언트 초기화 ---
gemini_client = None
try:
    gemini_client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
except:
    st.error("⚠️ Gemini API 키를 확인해주세요.")

groq_client = None
try:
    # Groq 클라이언트 초기화
    groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])
except:
    pass

try:
    treatment_db_content = st.secrets["TREATMENT_DB"]
except:
    st.error("⚠️ TREATMENT_DB 설정이 필요합니다.")
    st.stop()

# --- 4. 하이브리드 폴백 분석 로직 ---
def analyze_with_hybrid_fallback(prompt):
    # 1단계: Gemini 시도 (1.5 Flash 버전 순차 시도)
    gemini_models = ['models/gemini-1.5-flash', 'models/gemini-1.5-flash-8b']
    for model in gemini_models:
        try:
            response = gemini_client.models.generate_content(model=model, contents=prompt)
            return response.text, model.replace('models/', 'Gemini ')
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                continue
            break
            
    # 2단계: Gemini 실패 시 Groq 시도 (최상위 모델 사용)
    if groq_client:
        # Groq에서 지원하는 최상위 모델 리스트
        # llama-3.3-70b-versatile가 현재 Groq에서 가장 강력한 범용 모델입니다.
        try:
            chat_completion = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile", # 70B 모델은 오픈소스 중 최고 수준입니다.
                temperature=0.3, # 임상 분석을 위해 일관성 있는 답변 유도
            )
            return chat_completion.choices[0].message.content, "Groq (Llama-3.3-70B)"
        except Exception as e:
            raise Exception(f"모든 AI 서비스가 응답하지 않습니다. (Error: {e})")
    
    raise Exception("API 할당량 초과 및 보조 엔진 미설정")

# --- 5. 메인 UI (세로형 배치) ---
st.markdown('<div class="main-header">', unsafe_allow_html=True)
st.title("🩺 한방 임상 보조 시스템")
st.write(f"현재 환자: **#{st.session_state.patient_count}**")
st.markdown('</div>', unsafe_allow_html=True)

# [1] 입력 섹션
with st.container():
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("📝 대화 원문 입력")
    raw_text = st.text_area(
        "환자와의 대화 내용을 붙여넣으세요", 
        key='raw_text', 
        height=200, 
        placeholder="어디가 어떻게 불편하신가요?...",
        label_visibility="collapsed"
    )
    # 분석 버튼 (CSS로 크기 조절됨)
    analyze_btn = st.button("✨ AI 분석 및 처방 제안 시작")
    st.markdown('</div>', unsafe_allow_html=True)

# [2] 결과 출력 섹션 (분석 시 하단에 순차적 생성)
if analyze_btn and raw_text:
    try:
        # 1단계: SOAP 요약
        with st.spinner("SOAP 차트를 작성 중입니다..."):
            SOAP_PROMPT = f"한의사 보조 AI로서 아래 대화 원문을 SOAP 형식으로 요약하세요.\n[대화]: {raw_text}"
            soap_text, soap_model = analyze_with_hybrid_fallback(SOAP_PROMPT)
            
            st.markdown('<div class="stCard">', unsafe_allow_html=True)
            # 모델 정보 표시
            tag_type = "groq-tag" if "Groq" in soap_model else "gemini-tag"
            st.markdown(f"<div class='model-info-tag {tag_type}'>🤖 엔진: {soap_model}</div>", unsafe_allow_html=True)
            
            st.subheader("📋 SOAP 차트 요약")
            st.markdown(f'<div class="soap-box">{soap_text}</div>', unsafe_allow_html=True)
            
            st.download_button(
                "⬇️ SOAP 저장",
                data=soap_text,
                file_name=f"SOAP_{st.session_state.current_time}.txt",
                use_container_width=True
            )
            st.markdown('</div>', unsafe_allow_html=True)

        # 2단계: 치료 상세
        with st.spinner("치료 계획을 세우는 중..."):
            TREAT_PROMPT = f"""
            아래 SOAP 차트와 치료 DB를 바탕으로 상세 Plan을 작성하세요.
            혈자리는 '이름(코드) [이미지: URL]' 형식을 지키세요.
            [SOAP]: {soap_text}
            [DB]: {treatment_db_content}
            """
            treat_text, treat_model = analyze_with_hybrid_fallback(TREAT_PROMPT)

            st.markdown('<div class="stCard">', unsafe_allow_html=True)
            # 모델 정보 표시
            tag_type = "groq-tag" if "Groq" in treat_model else "gemini-tag"
            st.markdown(f"<div class='model-info-tag {tag_type}'>🤖 엔진: {treat_model}</div>", unsafe_allow_html=True)
            
            st.subheader("💡 추천 치료 및 처방")
            st.markdown(treat_text)
            
            # 혈자리 이미지 자동 표시
            img_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', treat_text, re.I)
            if img_patterns:
                st.divider()
                st.markdown("##### 🖼️ 혈자리 위치 가이드")
                for name, url in img_patterns:
                    st.image(url.strip(), caption=name, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

    except Exception as e:
        st.error(f"분석 중 오류가 발생했습니다: {e}")

# 하단 도구함
with st.sidebar:
    st.title("진료 도구")
    if st.button("🔄 다음 환자 (화면 비우기)"):
        clear_form()
        st.rerun()
    st.divider()
    if groq_client:
        st.success("✅ Groq 보조 엔진 가동 중")

st.divider()
st.caption(f"© 2025 임상 보조 시스템 | 접속 시간: {st.session_state.current_time}")
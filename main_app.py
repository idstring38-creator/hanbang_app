import streamlit as st
from google import genai
import re
import datetime
import time
from groq import Groq # Groq 라이브러리 추가

# --- 1. 페이지 설정 및 초기화 ---
st.set_page_config(
    page_title="한의사 임상 보조 시스템",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="auto"
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

# --- 2. 커스텀 CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Noto Sans KR', sans-serif;
    }
    
    .stCard {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border: 1px solid #e2e8f0;
        margin-bottom: 15px;
    }
    
    h1 { font-size: 1.5rem !important; font-weight: 700 !important; }
    h2 { font-size: 1.3rem !important; }
    
    p, span, div, label { 
        font-size: 0.92rem !important; 
        line-height: 1.6 !important; 
        word-break: keep-all;
    }

    .soap-box {
        background-color: #f1f5f9;
        border-left: 5px solid #3b82f6;
        padding: 12px;
        border-radius: 4px;
        margin-bottom: 10px;
        white-space: pre-wrap;
    }

    .stButton>button {
        width: 100%;
        border-radius: 10px;
        height: 3.5em;
        background-color: #2563eb;
        color: white !important;
        font-weight: bold;
        border: none;
    }
    
    .model-tag {
        font-size: 0.7rem !important;
        background-color: #e2e8f0;
        padding: 2px 6px;
        border-radius: 4px;
        color: #475569;
    }
    .groq-tag {
        background-color: #ffedd5;
        color: #9a3412;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. API 클라이언트 초기화 ---
# Gemini 설정
gemini_client = None
try:
    gemini_client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
except:
    st.error("⚠️ Gemini API 키를 확인해주세요.")

# Groq 설정 (새로 추가)
groq_client = None
try:
    groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])
except:
    # Groq 키가 없어도 일단 실행은 되게 함
    pass

try:
    treatment_db_content = st.secrets["TREATMENT_DB"]
except:
    st.error("⚠️ TREATMENT_DB 설정이 필요합니다.")
    st.stop()

# --- 4. 하이브리드 폴백 로직 (Gemini + Groq) ---
def analyze_with_hybrid_fallback(prompt):
    """
    1. Gemini Flash 계열 시도
    2. 실패 시 Groq (Llama 3.3 70B) 시도
    """
    # 1단계: Gemini 시도
    gemini_models = ['models/gemini-1.5-flash', 'models/gemini-1.5-flash-8b']
    
    for model in gemini_models:
        try:
            response = gemini_client.models.generate_content(model=model, contents=prompt)
            return response.text, model.replace('models/', '')
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                continue # 다음 Gemini 모델로
            break # 다른 에러면 Gemini 포기하고 Groq으로
            
    # 2단계: Gemini가 다 막혔다면 Groq 등판
    if groq_client:
        try:
            # Groq의 최신 강력한 모델인 llama-3.3-70b 사용
            chat_completion = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
            )
            return chat_completion.choices[0].message.content, "Groq (Llama 3.3)"
        except Exception as e:
            raise Exception(f"모든 AI 서비스가 응답하지 않습니다. 잠시 후 시도하세요. (Error: {e})")
    
    raise Exception("Gemini 할당량이 초과되었으며, Groq API 키가 설정되지 않았습니다.")

# --- 5. 사이드바 및 레이아웃 ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3774/3774299.png", width=60)
    st.title(f"환자 #{st.session_state.patient_count}")
    if groq_client:
        st.success("✅ Groq 보조 엔진 가동 중")
    else:
        st.warning("ℹ️ Groq 키 미설정 (Gemini만 사용)")
        
    if st.button("🔄 새 환자 진료 시작"):
        clear_form()
        st.rerun()

st.markdown("### 🩺 임상 보조 & SOAP 자동화")

col_in, col_out = st.columns([1, 1.2])

with col_in:
    st.markdown("#### 📝 환자 대화 입력")
    raw_text = st.text_area(
        "대화 원문", 
        key='raw_text', 
        height=250, 
        placeholder="대화 내용을 붙여넣으세요...",
        label_visibility="collapsed"
    )
    analyze_btn = st.button("✨ AI 분석 및 처방 제안")

# --- 6. 로직 실행 ---
if analyze_btn and raw_text:
    try:
        # 1단계: SOAP 생성
        with st.spinner("AI가 차트를 분석 중입니다..."):
            SOAP_PROMPT = f"한의사 보조 AI로서 아래 대화 원문을 SOAP 형식으로 요약하세요.\n[대화]: {raw_text}"
            soap_text, soap_model = analyze_with_hybrid_fallback(SOAP_PROMPT)
            
            match = re.search(r'^(A|CC):\s*(.*)', soap_text, re.M)
            filename_key = match.group(2).strip()[:10] if match else "진료기록"
            filename_key = re.sub(r'[^\w\s-]', '', filename_key).replace(' ', '_')
            
            with col_out:
                st.markdown("#### 🎯 분석 결과")
                st.markdown('<div class="stCard">', unsafe_allow_html=True)
                tag_class = "model-tag groq-tag" if "Groq" in soap_model else "model-tag"
                st.markdown(f"##### 📋 SOAP 차트 요약 <span class='{tag_class}'>{soap_model}</span>", unsafe_allow_html=True)
                st.markdown(f'<div class="soap-box">{soap_text}</div>', unsafe_allow_html=True)
                
                st.download_button(
                    "⬇️ 차트 다운로드",
                    data=soap_text,
                    file_name=f"SOAP_{filename_key}_{st.session_state.current_time}.txt",
                    use_container_width=True
                )
                st.markdown('</div>', unsafe_allow_html=True)

        # 2단계: 상세 치료법 제안
        with st.spinner("최적의 혈자리와 처방을 찾는 중..."):
            TREAT_PROMPT = f"""
            아래 SOAP 차트와 치료 DB를 바탕으로 상세 Plan을 작성하세요.
            혈자리는 '이름(코드) [이미지: URL]' 형식을 반드시 지키세요.
            [SOAP]: {soap_text}
            [DB]: {treatment_db_content}
            """
            treat_text, treat_model = analyze_with_hybrid_fallback(TREAT_PROMPT)

            with col_out:
                st.markdown('<div class="stCard">', unsafe_allow_html=True)
                tag_class = "model-tag groq-tag" if "Groq" in treat_model else "model-tag"
                st.markdown(f"##### 💡 추천 치료 상세 <span class='{tag_class}'>{treat_model}</span>", unsafe_allow_html=True)
                st.markdown(treat_text)
                
                img_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', treat_text, re.I)
                if img_patterns:
                    st.markdown("---")
                    st.markdown("##### 🖼️ 혈자리 가이드")
                    img_cols = st.columns(2)
                    for idx, (name, url) in enumerate(img_patterns):
                        with img_cols[idx % 2]:
                            st.image(url.strip(), caption=name, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)

    except Exception as e:
        st.error(f"❌ 분석 중 오류 발생: {e}")

elif not analyze_btn:
    with col_out:
        st.info("환자 대화를 입력하면 AI가 SOAP 정리와 혈자리 제안을 시작합니다.")
        st.image("https://cdn-icons-png.flaticon.com/512/3865/3865922.png", width=120)

st.divider()
st.caption(f"© 2025 임상 보조 시스템 | 현재 시간: {st.session_state.current_time}")
import streamlit as st
import google.generativeai as genai  # 라이브러리 호출 방식 변경
import re
import datetime
import time
from groq import Groq
import gspread
from google.oauth2.service_account import Credentials

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
    st.session_state.follow_up_questions = [] 
if 'raw_text' not in st.session_state:
    st.session_state.raw_text = ""
if 'additional_responses' not in st.session_state:
    st.session_state.additional_responses = {} 
if 'final_plan' not in st.session_state:
    st.session_state.final_plan = ""
if 'current_model' not in st.session_state:
    st.session_state.current_model = ""

def clear_form():
    st.session_state.raw_text = ""
    st.session_state.current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    st.session_state.patient_count += 1
    st.session_state.step = "input"
    st.session_state.soap_result = ""
    st.session_state.follow_up_questions = []
    st.session_state.additional_responses = {}
    st.session_state.final_plan = ""
    st.session_state.current_model = ""

# --- 2. 구글 시트 저장 함수 ---
def save_to_google_sheets(content):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        
        sheet = client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
        
        # 시트용 텍스트 가공: 이미지 태그를 클릭 가능한 링크 텍스트로 변환
        sheet_ready_content = re.sub(r'\[이미지:\s*(https?://[^\s\]]+)\]', r'\n(이미지 확인: \1)', content)
        
        now = datetime.datetime.now()
        row = [
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            st.session_state.patient_count,
            st.session_state.soap_result[:150], 
            sheet_ready_content 
        ]
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"구글 시트 저장 중 오류 발생: {e}")
        return False

# --- 3. 커스텀 CSS ---
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
        padding: 12px;
        border-radius: 8px;
        margin-bottom: 15px;
        white-space: pre-wrap;
        font-size: 0.92rem;
        line-height: 1.4;
    }

    .stButton>button {
        width: 100%;
        border-radius: 16px;
        height: 3.5em;
        background-color: #2563eb;
        color: white !important;
        font-weight: 800;
        border: none;
        box-shadow: 0 4px 10px rgba(37, 99, 235, 0.2);
    }
    
    .verify-btn>button {
        background-color: #059669 !important;
        box-shadow: 0 4px 10px rgba(5, 150, 105, 0.2) !important;
    }

    .q-item {
        background-color: #fffbeb;
        border: 1px solid #fde68a;
        padding: 12px;
        border-radius: 10px;
        color: #92400e;
        margin-top: 10px;
        font-size: 0.95rem;
        font-weight: 500;
    }
    
    .model-tag {
        font-size: 0.75rem;
        color: #64748b;
        background: #f1f5f9;
        padding: 2px 8px;
        border-radius: 4px;
        margin-bottom: 8px;
        display: inline-block;
    }
    
    .acu-caption {
        font-size: 1.1rem !important;
        font-weight: 700 !important;
        color: #0f172a !important; 
        text-align: center;
        margin-top: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 4. API 클라이언트 설정 (수정됨) ---
api_keys = []
# GEMINI_API_KEY가 리스트인지 문자열인지 확인하여 처리
if "GEMINI_API_KEY" in st.secrets:
    secret_val = st.secrets["GEMINI_API_KEY"]
    if isinstance(secret_val, list):
        api_keys = secret_val
    else:
        api_keys = [secret_val]
elif "GEMINI_API_KEYS" in st.secrets: # 예비용
    api_keys = st.secrets["GEMINI_API_KEYS"]

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

# --- 5. 분석 엔진 (수정됨) ---
def analyze_with_hybrid_fallback(prompt, system_instruction="당신은 노련한 한의사 보조 AI입니다."):
    # 1순위: Gemini 시도 (키 로테이션)
    gemini_models = ['gemini-1.5-flash', 'gemini-2.0-flash-exp'] # 1.5 flash 우선 사용
    
    for api_key in api_keys:
        try:
            # 매 반복마다 키 설정
            genai.configure(api_key=api_key)
            
            for model_name in gemini_models:
                try:
                    # 시스템 지침을 포함한 모델 생성
                    model = genai.GenerativeModel(
                        model_name=model_name,
                        system_instruction=system_instruction
                    )
                    
                    response = model.generate_content(prompt)
                    
                    if response and response.text:
                        st.session_state.current_model = f"{model_name} (Google)"
                        return response.text
                except Exception:
                    continue # 모델 변경 후 재시도
        except Exception:
            continue # 키 변경 후 재시도
            
    # 2순위: Groq (Fallback)
    if groq_client:
        try:
            model_name = "llama-3.3-70b-versatile"
            chat_completion = groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": f"{system_instruction}\n당신은 제공된 DB를 엄격히 준수하며, 논리적이고 세밀한 한의학적 분석을 수행해야 합니다. 출력 형식을 절대로 생략하지 마세요."},
                    {"role": "user", "content": prompt}
                ],
                model=model_name,
                temperature=0.2,
            )
            st.session_state.current_model = f"{model_name} (Groq)"
            return chat_completion.choices[0].message.content
        except Exception as e:
            st.error(f"Groq 호출 실패: {e}")
    
    raise Exception("모든 API 키와 모델 호출에 실패했습니다.")

def clean_newlines(text):
    if not text: return ""
    return re.sub(r'\n{3,}', '\n\n', text).strip()

# --- 6. UI 및 로직 ---
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
                    다음 대화 원문을 바탕으로 '문진 단계'를 수행하세요.
                    
                    **출력 형식 필수 지침**:
                    1. [SOAP 요약]: 환자의 증상을 SOAP 형식으로 요약. 입력되지 않은 정보는 절대 상상해서 적지 마세요.
                    2. [추가 확인 사항]: 육기 진단을 위해 필요한 질문을 번호를 매겨 작성. (예: 1. 질문내용)
                    
                    **주의**: '추가 확인 사항' 섹션에는 도입부 없이 질문 리스트만 포함하세요.
                    
                    [대화 원문]: {raw_text}
                    """
                    try:
                        result = analyze_with_hybrid_fallback(FIRST_PROMPT)
                        
                        if "[추가 확인 사항]" in result:
                            parts = result.split("[추가 확인 사항]")
                            st.session_state.soap_result = clean_newlines(parts[0].replace("[SOAP 요약]", "").strip())
                            questions_raw = parts[1].strip()
                            q_list = re.split(r'\n?\d+\.\s*', questions_raw)
                            st.session_state.follow_up_questions = [q.strip() for q in q_list if len(q.strip()) > 5]
                        else:
                            st.session_state.soap_result = clean_newlines(result.replace("[SOAP 요약]", "").strip())
                            st.session_state.follow_up_questions = []
                        
                        st.session_state.raw_text = raw_text
                        st.session_state.step = "verify"
                        st.rerun()
                    except Exception as e:
                        st.error(f"분석 중 오류 발생: {e}")
            else:
                st.warning("내용을 입력해주세요.")
        st.markdown('</div>', unsafe_allow_html=True)

# [Step 2] 추가 문진 확인
elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.markdown(f'<div class="model-tag">🤖 분석 모델: {st.session_state.current_model}</div>', unsafe_allow_html=True)
    st.subheader("📋 1차 SOAP 요약")
    st.markdown(f'<div class="soap-box">{st.session_state.soap_result}</div>', unsafe_allow_html=True)
    
    if st.session_state.follow_up_questions:
        st.subheader("🔍 추가 확인 사항")
        for i, question in enumerate(st.session_state.follow_up_questions):
            st.markdown(f'<div class="q-item">{i+1}. {question}</div>', unsafe_allow_html=True)
            st.session_state.additional_responses[f"q_{i}"] = st.text_input(
                f"질문 {i+1} 답변", 
                key=f"input_{i}", 
                label_visibility="collapsed",
                placeholder="답변을 입력하세요..."
            )
    
    st.markdown('<div class="verify-btn" style="margin-top:20px;">', unsafe_allow_html=True)
    if st.button("✅ 최종 확인 및 처방 생성"):
        combined_answers = "\n".join([f"Q: {q}\nA: {st.session_state.additional_responses.get(f'q_{i}', '미응답')}" 
                                      for i, q in enumerate(st.session_state.follow_up_questions)])
        st.session_state.additional_input = combined_answers if combined_answers else "특이사항 없음"
        st.session_state.step = "result"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# [Step 3] 최종 결과 출력
elif st.session_state.step == "result":
    if not st.session_state.final_plan:
        with st.spinner("최종 치료 계획을 수립 중..."):
            FINAL_PROMPT = f"""
            [치료 DB]: {treatment_db_content}
            [환자 정보]: {st.session_state.raw_text}
            [1차 SOAP 요약]: {st.session_state.soap_result}
            [추가 답변 정보]: {st.session_state.additional_input}
            
            위 정보를 바탕으로 한의사 원장님을 위한 최종 진단 및 치료 계획을 수립하세요.
            
            **반드시 다음 순서와 지침을 엄격히 준수하여 출력하세요**:

            1. **[질환 분석]**: 
               - 양방질환명과 한방질환명을 가장 먼저 제시하세요.
               - 왜 그렇게 추론했는지 환자의 증상과 육기(六氣)적 관점에서 최대한 자세히 서술하세요.

            2. **[상세 SOAP 차트]**:
               - 차트에 그대로 복사해 붙여넣을 수 있도록 상세하게 작성하세요.
               - 단, 환자가 말하지 않은 허위 정보(예: 맥진 결과, 설진 결과 등 확인 안 된 것)는 절대 적지 마세요.

            3. **[원인 분석]**: 
               - 환자의 현재 상태를 유발한 근본 원인을 증상과 추가 정보를 통합하여 논리적으로 서술하세요.

            4. **[처방]**:
               - DB에 기반한 원락극 혈자리 처방을 제시하세요.
               - 혈자리 이름과 코드를 명확히 표기하세요. (예: 양로(SI6))
               - **취혈 방향(동측/대측)**과 **그 이유**를 이 섹션에 통합하여 간략히 설명하세요.
               - 형식: '혈자리명(코드) / 취혈방향 [이미지: URL] - 이유: 설명'

            5. **[생활 지도]**:
               - 현재 환자에게 필요한 일반적이고 보편적인 생활 습관 교정 및 지도 사안을 출력하세요.

            **출력 예시**:
            양로(SI6) / 대측 [이미지: https://...] - 이유: 태양한수의 극혈로서 급성 인대 손상을 제어하기 위해 대측을 취혈합니다.
            """
            st.session_state.final_plan = analyze_with_hybrid_fallback(FINAL_PROMPT)

    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.markdown(f'<div class="model-tag">🤖 최종 분석 모델: {st.session_state.current_model}</div>', unsafe_allow_html=True)
    st.subheader("💡 최종 진단 및 치료 계획")
    
    # 이미지 정보를 제외한 본문 출력
    display_text = re.sub(r'\S+\s*/\s*\S+\s*\[이미지:\s*https?:\/\/[^\s\]]+\]', '', st.session_state.final_plan)
    st.markdown(display_text)
    
    # 혈자리 이미지 및 취혈 방향 렌더링
    img_patterns = re.findall(r'([^\s\[]+(?:\s*/\s*[^\s\[]+)?)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', st.session_state.final_plan)
    if img_patterns:
        st.divider()
        st.markdown("##### 🖼️ 혈자리 가이드")
        cols = st.columns(2)
        for idx, (label, url) in enumerate(img_patterns):
            with cols[idx % 2]:
                st.image(url.strip(), use_container_width=True)
                st.markdown(f'<div class="acu-caption">{label}</div>', unsafe_allow_html=True)

    st.divider()
    
    col_save, col_next = st.columns(2)
    with col_save:
        if st.button("📲 모바일 시트 전송", type="primary"):
            with st.spinner("시트 저장 중..."):
                if save_to_google_sheets(st.session_state.final_plan):
                    st.success("전송 완료!")
    
    with col_next:
        if st.button("🔄 다음 환자 진료"):
            clear_form()
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

with st.sidebar:
    if st.button("🏠 홈으로 (초기화)"):
        clear_form()
        st.rerun()

st.caption(f"© 2025 임상 보조 시스템 | {st.session_state.current_time}")

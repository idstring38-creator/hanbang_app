import streamlit as st
import google.generativeai as genai 
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

if 'patient_count' not in st.session_state:
    st.session_state.patient_count = 1
if 'current_time' not in st.session_state:
    st.session_state.current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
if 'step' not in st.session_state:
    st.session_state.step = "input" 
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
        sheet_ready_content = re.sub(r'\[이미지:\s*(https?://[^\s\]]+)\]', r'\n(이미지 확인: \1)', content)
        now = datetime.datetime.now()
        row = [now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), st.session_state.patient_count, st.session_state.soap_result[:150], sheet_ready_content]
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"구글 시트 저장 중 오류 발생: {e}")
        return False

# --- 3. 커스텀 CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; background-color: #f8fafc; }
    .stCard { background-color: #ffffff; border-radius: 16px; padding: 25px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border: 1px solid #e2e8f0; margin-bottom: 20px; }
    .main-header { text-align: center; margin-bottom: 20px; }
    .q-item { background-color: #fefce8; border: 1px solid #fef08a; padding: 15px; border-radius: 12px; color: #854d0e; margin-top: 15px; font-size: 1rem; font-weight: 600; }
    .model-tag { font-size: 0.75rem; color: #64748b; background: #f1f5f9; padding: 2px 8px; border-radius: 4px; margin-bottom: 8px; display: inline-block; }
    .acu-caption { font-size: 1.1rem !important; font-weight: 700 !important; color: #0f172a !important; text-align: center; margin-top: 5px; }
    .stButton>button { width: 100%; border-radius: 16px; height: 3.5em; background-color: #2563eb; color: white !important; font-weight: 800; border: none; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. API 클라이언트 설정 ---
api_keys = []
if "GEMINI_API_KEY" in st.secrets:
    raw_keys = st.secrets["GEMINI_API_KEY"]
    api_keys = raw_keys if isinstance(raw_keys, list) else [raw_keys]

groq_client = None
try:
    groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])
except:
    pass

treatment_db_content = st.secrets.get("TREATMENT_DB", "DB 정보가 없습니다.")

# --- 5. 분석 엔진 ---
def analyze_with_hybrid_fallback(prompt, system_instruction="당신은 노련한 한의사 보조 AI입니다."):
    gemini_models = ['models/gemini-2.0-flash-exp', 'models/gemini-1.5-flash']
    
    for api_key in api_keys:
        try:
            genai.configure(api_key=api_key)
            for model_name in gemini_models:
                try:
                    model = genai.GenerativeModel(model_name=model_name, system_instruction=system_instruction)
                    response = model.generate_content(prompt)
                    if response and response.text:
                        display_name = model_name.split('/')[-1]
                        st.session_state.current_model = f"{display_name} (Google)"
                        return response.text
                except: continue
        except: continue
            
    if groq_client:
        try:
            model_name = "llama-3.3-70b-versatile"
            chat_completion = groq_client.chat.completions.create(
                messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}],
                model=model_name, temperature=0.2,
            )
            st.session_state.current_model = f"{model_name} (Groq)"
            return chat_completion.choices[0].message.content
        except: pass
    
    raise Exception("AI 모델 호출 실패")

# --- 6. UI 로직 ---
st.markdown('<div class="main-header">', unsafe_allow_html=True)
st.title("🩺 한방 임상 보조 시스템")
st.write(f"현재 환자: **#{st.session_state.patient_count}**")
st.markdown('</div>', unsafe_allow_html=True)

if st.session_state.step == "input":
    with st.container():
        st.markdown('<div class="stCard">', unsafe_allow_html=True)
        st.subheader("📝 대화 원문 입력")
        raw_text = st.text_area("증상을 입력하세요", key='raw_text_input', height=200, label_visibility="collapsed")
        if st.button("✨ 1차 분석 및 문진 확인"):
            if raw_text:
                with st.spinner("증상을 분석 중입니다..."):
                    FIRST_PROMPT = f"다음 대화 원문을 바탕으로 '문진 단계'를 수행하세요.\n\n**출력 형식 필수 지침**:\n1. [SOAP 요약]: 요약 내용\n2. [추가 확인 사항]: 질문 리스트\n\n[대화 원문]: {raw_text}"
                    result = analyze_with_hybrid_fallback(FIRST_PROMPT)
                    if "[추가 확인 사항]" in result:
                        parts = result.split("[추가 확인 사항]")
                        st.session_state.soap_result = parts[0].replace("[SOAP 요약]", "").strip()
                        q_list = re.split(r'\n\d+\.\s*', parts[1].strip())
                        st.session_state.follow_up_questions = [q.strip() for q in q_list if len(q.strip()) > 5]
                    else:
                        st.session_state.soap_result = result.replace("[SOAP 요약]", "").strip()
                    st.session_state.raw_text = raw_text
                    st.session_state.step = "verify"
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.markdown(f'<div class="model-tag">🤖 분석 모델: {st.session_state.current_model}</div>', unsafe_allow_html=True)
    st.subheader("🔍 추가 문진이 필요합니다")
    st.write("진단을 위해 아래 질문들에 대해 답변해 주세요.")
    
    # 1. 질문마다 개별 답변 칸 생성
    if st.session_state.follow_up_questions:
        for i, question in enumerate(st.session_state.follow_up_questions):
            st.markdown(f'<div class="q-item">질문 {i+1}. {question}</div>', unsafe_allow_html=True)
            # 세션 상태에 저장하여 답변 유지
            st.session_state.additional_responses[f"q_{i}"] = st.text_input(
                f"질문 {i+1}에 대한 답변", 
                key=f"input_box_{i}", 
                placeholder="환자의 답변을 입력하세요...",
                label_visibility="collapsed"
            )
    else:
        st.info("추가 확인 사항이 없습니다. 바로 처방을 생성할 수 있습니다.")

    if st.button("✅ 답변 완료 및 처방 생성"):
        # 입력된 답변들을 프롬프트용 텍스트로 결합
        responses_text = ""
        for i, q in enumerate(st.session_state.follow_up_questions):
            ans = st.session_state.additional_responses.get(f"q_{i}", "특이사항 없음")
            responses_text += f"질문: {q}\n답변: {ans}\n\n"
        st.session_state.additional_input = responses_text
        st.session_state.step = "result"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.step == "result":
    if not st.session_state.final_plan:
        with st.spinner("최종 치료 계획 수립 중..."):
            FINAL_PROMPT = f"[치료 DB]: {treatment_db_content}\n[1차 요약]: {st.session_state.soap_result}\n[추가 답변 내역]:\n{st.session_state.additional_input}\n\n위 정보를 종합하여 최종 SOAP 진단과 처방 계획을 수립하세요."
            st.session_state.final_plan = analyze_with_hybrid_fallback(FINAL_PROMPT)

    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.markdown(f'<div class="model-tag">🤖 최종 모델: {st.session_state.current_model}</div>', unsafe_allow_html=True)
    st.subheader("💡 최종 진단 및 치료 계획")
    # 이미지 태그를 제외한 텍스트 출력
    display_text = re.sub(r'\S+\s*/\s*\S+\s*\[이미지:\s*https?:\/\/[^\s\]]+\]', '', st.session_state.final_plan)
    st.markdown(display_text)
    
    # 이미지 출력 로직
    img_patterns = re.findall(r'([^\s\[]+(?:\s*/\s*[^\s\[]+)?)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', st.session_state.final_plan)
    if img_patterns:
        st.divider()
        cols = st.columns(2)
        for idx, (label, url) in enumerate(img_patterns):
            with cols[idx % 2]:
                st.image(url.strip(), use_container_width=True)
                st.markdown(f'<div class="acu-caption">{label}</div>', unsafe_allow_html=True)
    
    if st.button("📲 모바일 시트 전송"):
        if save_to_google_sheets(st.session_state.final_plan): st.success("전송 완료!")
    if st.button("🔄 다음 환자 진료"):
        clear_form()
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

with st.sidebar:
    if st.button("🏠 홈으로 (초기화)"):
        clear_form()
        st.rerun()

import streamlit as st
import google.generativeai as genai 
import re
import datetime
import uuid
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 설정 및 초기화 ---
st.set_page_config(page_title="한의사 임상 보조 시스템", page_icon="🩺", layout="centered")

if 'step' not in st.session_state: st.session_state.step = "input"
if 'patient_info' not in st.session_state: st.session_state.patient_info = {"name": "", "gender": "미선택", "birth_year": ""}
if 'follow_up_questions' not in st.session_state: st.session_state.follow_up_questions = []
if 'responses' not in st.session_state: st.session_state.responses = {}
if 'final_plan' not in st.session_state: st.session_state.final_plan = ""

# --- 2. 커스텀 CSS (크고 파란색 버튼 및 UI) ---
st.markdown("""
    <style>
    .stCard { background-color: #ffffff; border-radius: 16px; padding: 25px; border: 1px solid #e2e8f0; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    
    /* 버튼 스타일: 크고 파란색 */
    div.stButton > button {
        background-color: #1d4ed8 !important;
        color: white !important;
        font-size: 1.2rem !important;
        font-weight: 700 !important;
        height: 4em !important;
        width: 100% !important;
        border-radius: 12px !important;
        border: none !important;
        box-shadow: 0 4px 12px rgba(29, 78, 216, 0.3) !important;
        transition: all 0.2s ease;
    }
    div.stButton > button:hover {
        background-color: #1e40af !important;
        box-shadow: 0 6px 16px rgba(29, 78, 216, 0.4) !important;
        transform: translateY(-2px);
    }
    
    .q-item { background-color: #f8fafc; padding: 15px; border-radius: 10px; border-left: 5px solid #3b82f6; margin-top: 10px; font-weight: 500; }
    </style>
    """, unsafe_allow_html=True)

def calculate_age(birth_year):
    try: return 2025 - int(birth_year) + 1
    except: return "미상"

# --- 3. UI 로직 ---
st.title("🩺 한방 임상 보조 시스템")

if st.session_state.step == "input":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("👤 환자 정보 및 증상 입력")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1: name = st.text_input("이름", placeholder="성함")
    with c2: gender = st.selectbox("성별", ["미선택", "남성", "여성"])
    with c3: birth_year = st.text_input("출생년도", placeholder="예: 1985")
    raw_text = st.text_area("주소증 및 현재 증상을 자유롭게 입력하세요", height=150)
    
    if st.button("✨ 분석 시작 및 정밀 문진 생성"):
        if raw_text and birth_year:
            st.session_state.patient_info = {"name": name, "gender": gender, "birth_year": birth_year}
            with st.spinner("AI가 증상을 분석하여 질문을 생성하고 있습니다..."):
                try:
                    genai.configure(api_key=st.secrets["GEMINI_API_KEY"][0])
                    model = genai.GenerativeModel('models/gemini-2.0-flash-exp')
                    age = calculate_age(birth_year)
                    
                    PROMPT = f"""환자 정보: {name}({gender}, {age}세)\n입력된 증상: {raw_text}\n\n
                    [지침]: 위 내용을 바탕으로 한의학적 변증과 정확한 진단을 위해 필요한 추가 질문을 생성하세요. 
                    - 질문은 반드시 한 줄에 하나씩 작성하고 물음표(?)로 끝내세요.
                    - **반드시 5개 이상의 질문을 생성해야 합니다.** 데이터가 부족하면 발병일, 통증 양상, 악화 요인, 소화/수면 상태 등 기초 문진을 포함하세요.
                    
                    [SOAP 요약]: ...
                    [추가 확인 사항]: 질문들..."""
                    
                    result = model.generate_content(PROMPT).text
                    if "[추가 확인 사항]" in result:
                        parts = result.split("[추가 확인 사항]")
                        qs = [q.strip() for q in re.split(r'\n|(?<=\?)\s*', parts[1]) if '?' in q]
                        
                        # 질문이 5개 미만일 경우 강제 보충
                        default_qs = [
                            "증상이 정확히 언제부터 시작되었나요?",
                            "통증이나 불편함의 양상은 어떠한가요? (쑤심, 저림, 무거움 등)",
                            "특별히 증상이 심해지거나 완화되는 상황이 있나요?",
                            "평소 소화 상태나 대소변 상태는 어떠신가요?",
                            "수면의 질은 어떠하며, 아침에 일어나실 때 컨디션은 어떠신가요?"
                        ]
                        final_qs = qs + [dq for dq in default_qs if dq not in qs]
                        st.session_state.follow_up_questions = final_qs[:max(5, len(qs))]
                        
                    st.session_state.step = "verify"
                    st.rerun()
                except Exception as e:
                    st.error(f"오류가 발생했습니다: {e}")
    st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("🔍 정밀 문진 (최종 진단을 위해 답변해 주세요)")
    
    for i, q in enumerate(st.session_state.follow_up_questions):
        st.markdown(f'<div class="q-item">{q}</div>', unsafe_allow_html=True)
        st.session_state.responses[f"q_{i}"] = st.text_input(f"답변 {i+1}", key=f"ans_{i}", placeholder="내용을 입력하세요...")
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("✅ 분석 완료 및 처방 확인"):
        st.session_state.step = "result"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# (이후 result 단계 로직은 기존과 동일하게 유지됩니다)

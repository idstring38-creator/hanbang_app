import streamlit as st
from google import genai
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
        
        # 시트용 텍스트 가공: 이미지 태그 제거 및 줄바꿈 정리
        sheet_content = re.sub(r'\[이미지:.*?\]', '', content)
        
        now = datetime.datetime.now()
        row = [
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            st.session_state.patient_count,
            st.session_state.soap_result[:150], 
            sheet_content.strip() 
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
        padding: 24px;
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
        font-size: 0.95rem;
        line-height: 1.6;
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
    
    h3 {
        color: #1e3a8a;
        border-bottom: 2px solid #e2e8f0;
        padding-bottom: 8px;
        margin-top: 20px;
        margin-bottom: 15px;
        font-size: 1.3rem;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 4. API 클라이언트 설정 ---
api_keys = []
if "GEMINI_API_KEYS" in st.secrets:
    raw_keys = st.secrets["GEMINI_API_KEYS"]
    if isinstance(raw_keys, list):
        api_keys = raw_keys
    else:
        api_keys = [k.strip() for k in str(raw_keys).split(",") if k.strip()]
elif "GEMINI_API_KEY" in st.secrets:
    api_keys = [st.secrets["GEMINI_API_KEY"]]

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

# --- 5. 분석 엔진 ---
def analyze_with_hybrid_fallback(prompt, system_instruction="당신은 노련한 한의사 보조 AI입니다."):
    gemini_models = ['gemini-2.0-flash-exp', 'gemini-1.5-flash']
    
    for api_key in api_keys:
        try:
            client = genai.Client(api_key=api_key)
            for model_id in gemini_models:
                try:
                    response = client.models.generate_content(
                        model=model_id, 
                        contents=prompt,
                        config={'system_instruction': system_instruction}
                    )
                    if response and response.text:
                        st.session_state.current_model = f"{model_id} (Active)"
                        return response.text
                except Exception:
                    continue
        except Exception:
            continue
            
    if groq_client:
        try:
            model_name = "llama-3.3-70b-versatile"
            chat_completion = groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": f"{system_instruction}\nDB를 엄격히 준수하고 논리적으로 분석하세요."},
                    {"role": "user", "content": prompt}
                ],
                model=model_name,
                temperature=0.2,
            )
            st.session_state.current_model = f"{model_name} (Fallback)"
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
                    
                    **지침**:
                    1. [SOAP 요약]: 환자의 증상을 SOAP 형식으로 요약.
                    2. [추가 확인 사항]: 육기 진단을 위해 꼭 필요한 질문 리스트만 작성(번호 매기기). 만약 정보가 충분하다면 '없음' 작성.
                    
                    [대화 원문]: {raw_text}
                    """
                    try:
                        result = analyze_with_hybrid_fallback(FIRST_PROMPT)
                        
                        if "[추가 확인 사항]" in result:
                            parts = result.split("[추가 확인 사항]")
                            st.session_state.soap_result = clean_newlines(parts[0].replace("[SOAP 요약]", "").strip())
                            questions_raw = parts[1].strip()
                            q_list = re.split(r'\n?\d+\.\s*', questions_raw)
                            # 필터링 로직 강화
                            st.session_state.follow_up_questions = [
                                q.strip() for q in q_list 
                                if len(q.strip()) > 5 and "없음" not in q and "확인 사항" not in q
                            ]
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
    else:
        st.info("추가로 확인할 사항이 없습니다. 바로 처방을 생성합니다.")
    
    st.markdown('<div class="verify-btn" style="margin-top:20px;">', unsafe_allow_html=True)
    if st.button("✅ 최종 확인 및 처방 생성"):
        combined_answers = "\n".join([f"Q: {q}\nA: {st.session_state.additional_responses.get(f'q_{i}', '특이사항 없음')}" 
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
            [1차 SOAP]: {st.session_state.soap_result}
            [추가 문진]: {st.session_state.additional_input}
            
            위 정보를 바탕으로 한의사 원장님을 위한 최종 진단 리포트를 작성하세요.
            **반드시 아래 목차와 형식을 엄격히 준수하세요**:

            ### 1. 추정 진단 (의심 질환)
            * **양방 의심 질환**: (명확한 질환명 제시)
            * **한방 변증(육기)**: (예: 궐음풍목 태과, 소양상화 불급 등)
            * **상세 추론 근거**: 환자의 주소증과 문진 결과를 바탕으로 왜 이 질환으로 판단했는지 양방 병리와 육기 이론을 결합하여 자세히 서술하세요.

            ### 2. 진료기록부 (SOAP)
            * 차트에 바로 복사할 수 있도록 S/O/A/P 형식을 갖추어 작성하세요.
            * **주의**: 환자가 언급하지 않은 맥진, 설진 등의 정보는 절대 포함하지 마세요. 오직 확인된 팩트만 기재하세요.

            ### 3. 원인 분석
            * '증상 분석'과 '추가 정보'를 통합하여, 이 질환이 발생하게 된 근본 원인과 현재 상태를 논리적으로 설명하세요.

            ### 4. 최종 침구 처방
            * 치료 DB에 기반하여 혈자리, 취혈 방향, 선혈 이유를 통합하여 서술하세요.
            * **형식**: `● 혈자리명(코드) / 취혈방향 (동측 or 대측) : 선혈 이유 상세 서술`
            * (예시: ● **내관(PC6)** / 동측 : 급성 근육통(궐음)의 락혈로서 기체와 압력을 해소하기 위함입니다.)

            ### 5. 생활 지도
            * 예후 대신, 환자가 일상에서 실천해야 할 구체적이고 보편적인 생활 습관 교정 및 주의사항을 제시하세요.

            ---
            (시스템 처리용: 맨 마지막 줄에 `이미지: 혈자리명(코드) [이미지: URL]` 리스트를 나열하세요.)
            """
            try:
                st.session_state.final_plan = analyze_with_hybrid_fallback(FINAL_PROMPT)
            except Exception as e:
                st.error(f"최종 분석 중 오류: {e}")

    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.markdown(f'<div class="model-tag">🤖 최종 분석 모델: {st.session_state.current_model}</div>', unsafe_allow_html=True)
    st.subheader("💡 최종 진단 및 치료 계획")
    
    # 텍스트 본문 출력 (이미지 링크 제거)
    display_text = re.sub(r'이미지:.*\[이미지:.*\]', '', st.session_state.final_plan)
    display_text = re.sub(r'\[이미지:.*\]', '', display_text) 
    st.markdown(display_text)
    
    # 혈자리 이미지 렌더링
    img_patterns = re.findall(r'([^\s\[:]+(?:\([^\)]+\))?)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', st.session_state.final_plan)
    if img_patterns:
        st.divider()
        st.markdown("##### 🖼️ 혈자리 위치 가이드")
        seen_urls = set()
        cols = st.columns(2)
        for idx, (label, url) in enumerate(img_patterns):
            clean_url = url.strip()
            if clean_url not in seen_urls:
                with cols[idx % 2]:
                    st.image(clean_url, use_container_width=True)
                    st.markdown(f'<div class="acu-caption">{label}</div>', unsafe_allow_html=True)
                seen_urls.add(clean_url)

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

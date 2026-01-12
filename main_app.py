import streamlit as st
import google.generativeai as genai 
import re
import datetime
import uuid
import gspread
from google.oauth2.service_account import Credentials
import streamlit.components.v1 as components
from groq import Groq # Groq 라이브러리 필수

# --- 1. 페이지 설정 및 초기화 ---
st.set_page_config(
    page_title="한의사 임상 보조 시스템", 
    page_icon="🩺", 
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 세션 상태 초기화
for key in ['step', 'patient_info', 'follow_up_questions', 'responses', 'final_plan', 'shared_link', 'raw_text', 'current_model']:
    if key not in st.session_state:
        if key == 'step': st.session_state[key] = "input"
        elif key == 'patient_info': st.session_state[key] = {"name": "", "gender": "미선택", "birth_year": ""}
        elif key in ['follow_up_questions', 'responses']: st.session_state[key] = [] if key=='follow_up_questions' else {}
        else: st.session_state[key] = ""

MY_APP_URL = "https://idstring.streamlit.app/" 

# --- 2. API 클라이언트 및 DB 설정 (오류 해결의 핵심) ---

# (1) Gemini API 키 로드 (리스트/문자열 모두 대응)
api_keys = []
if "GEMINI_API_KEYS" in st.secrets:
    raw = st.secrets["GEMINI_API_KEYS"]
    api_keys = raw if isinstance(raw, list) else [k.strip() for k in str(raw).split(",") if k.strip()]
elif "GEMINI_API_KEY" in st.secrets:
    raw = st.secrets["GEMINI_API_KEY"]
    api_keys = raw if isinstance(raw, list) else [raw]

# (2) Groq 클라이언트
groq_client = None
try:
    groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])
except:
    pass

# (3) 치료법 DB 로드
try:
    treatment_db_content = st.secrets["TREATMENT_DB"]
except:
    st.error("⚠️ TREATMENT_DB 설정이 필요합니다.")
    st.stop()

# (4) 구글 시트 연동
def get_storage_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
    except: return None

# --- 3. 하이브리드 분석 엔진 (핵심 로직) ---
def analyze_with_hybrid_fallback(prompt, system_instruction="당신은 노련한 한의사 보조 AI입니다."):
    # 1순위: Gemini 모델들 (2.0 -> 1.5)
    gemini_models = ['gemini-2.0-flash-exp', 'gemini-1.5-flash']
    
    # 키 로테이션 및 모델 순회
    for api_key in api_keys:
        try:
            genai.configure(api_key=api_key)
            for model_name in gemini_models:
                try:
                    model = genai.GenerativeModel(
                        model_name,
                        system_instruction=system_instruction
                    )
                    response = model.generate_content(prompt)
                    if response and response.text:
                        st.session_state.current_model = f"{model_name} (Google)"
                        return response.text
                except Exception:
                    continue # 다음 모델 시도
        except Exception:
            continue # 다음 키 시도

    # 2순위: Groq (Google 실패 시)
    if groq_client:
        try:
            chat_completion = groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": f"{system_instruction} DB를 엄격히 준수하세요."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.3,
            )
            st.session_state.current_model = "Llama-3.3 (Groq)"
            return chat_completion.choices[0].message.content
        except Exception as e:
            st.error(f"Groq 오류: {e}")

    raise Exception("모든 AI 엔진 연결 실패 (키/할당량 확인 필요)")

# --- 헬퍼 함수 ---
def render_text_with_images(text):
    pattern = r'\[이미지:\s*(https?://[^\s\]]+)\]'
    replacement = r'<br><img src="\1" style="width: 100%; max-width: 400px; border-radius: 10px; margin: 10px 0; box-shadow: 0 2px 5px rgba(0,0,0,0.1);"><br>'
    return re.sub(pattern, replacement, text)

# --- 4. [공유 모드 확인] ---
query_params = st.query_params
shared_id = query_params.get("view")

if shared_id:
    sheet = get_storage_sheet()
    if sheet:
        try:
            cell = sheet.find(shared_id)
            if cell:
                row_data = sheet.row_values(cell.row)
                st.markdown(f"### 🩺 {row_data[2]}님 최종 진단결과")
                st.markdown('<div style="background-color: white; padding: 25px; border-radius: 16px; border: 1px solid #e2e8f0;">', unsafe_allow_html=True)
                raw_content = row_data[4].replace("```html", "").replace("```", "")
                processed_content = render_text_with_images(raw_content)
                st.markdown(processed_content, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        except: st.error("기록을 찾을 수 없습니다.")
    
    st.write("")
    if st.button("🏠 새로운 진단하러 가기"):
        st.query_params.clear()
        st.rerun()
    st.stop()

# --- 5. 커스텀 CSS ---
st.markdown("""
    <style>
    .stCard { background-color: #ffffff; border-radius: 16px; padding: 25px; border: 1px solid #e2e8f0; margin-bottom: 20px; }
    .result-title { 
        color: #0056b3 !important; 
        font-size: 1.5rem !important; 
        font-weight: 900 !important; 
        border-left: 6px solid #0056b3; 
        padding-left: 12px; 
        margin-top: 40px !important; 
        margin-bottom: 15px !important;
        background-color: #f8fbff;
        padding-top: 8px;
        padding-bottom: 8px;
        border-radius: 0 5px 5px 0;
    }
    div.stButton > button {
        background-color: #1d4ed8 !important; color: white !important;
        font-size: 1.1rem !important; font-weight: 700 !important;
        height: 3.5em !important; width: 100% !important;
        border-radius: 12px !important; border: none !important;
        box-shadow: 0 4px 10px rgba(29, 78, 216, 0.2) !important;
    }
    .q-item { background-color: #f8fafc; padding: 15px; border-radius: 10px; border-left: 5px solid #3b82f6; margin-top: 10px; font-weight: 600; }
    .model-tag { font-size: 0.8rem; color: #64748b; margin-bottom: 10px; display: block; text-align: right; }
    </style>
    """, unsafe_allow_html=True)

def calculate_age(birth_year):
    try: return datetime.date.today().year - int(birth_year) + 1
    except: return "미상"

# --- 6. UI 로직 ---

if st.session_state.step == "input":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.subheader("👤 환자 정보 및 증상 입력")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1: name = st.text_input("이름", placeholder="성함")
    with c2: gender = st.selectbox("성별", ["남성", "여성", "미선택"])
    with c3: birth_year = st.text_input("출생년도", placeholder="예: 1985")
    raw_text = st.text_area("주소증 입력", height=150, placeholder="환자의 주요 증상을 최대한 자세히 입력해주세요.")
    
    if st.button("✨ 분석 시작 및 문진 생성"):
        if raw_text:
            st.session_state.patient_info = {"name": name, "gender": gender, "birth_year": birth_year}
            with st.spinner("증상을 분석하여 핵심 질문을 생성하고 있습니다..."):
                PROMPT = f"""
                환자: {name}, 증상: {raw_text}
                [지침]: 한의학적 육기(六氣) 진단을 확정하기 위해 환자에게 물어봐야 할 가장 중요한 질문 5가지를 생성하세요.
                각 질문은 반드시 물음표(?)로 끝나야 하며, 번호를 붙이지 말고 줄바꿈으로 구분하세요.
                """
                try:
                    # 여기서 하이브리드 엔진 사용
                    res = analyze_with_hybrid_fallback(PROMPT)
                    
                    # 결과 파싱 (질문 추출)
                    qs = [q.strip() for q in re.split(r'\n', res) if '?' in q and len(q) > 5]
                    
                    if not qs: # 질문 생성 실패 시 기본값
                        qs = ["증상이 언제부터 시작되었나요?", "통증의 양상은 어떤가요?", "악화되거나 완화되는 요인이 있나요?"]
                        
                    st.session_state.follow_up_questions = qs[:5]
                    st.session_state.raw_text = raw_text
                    st.session_state.step = "verify"
                    st.rerun()
                except Exception as e:
                    st.error(f"오류 상세: {e}")
                    st.error("API 연결에 실패했습니다. 키 설정을 확인해주세요.")
    st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.step == "verify":
    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    st.markdown(f'<span class="model-tag">🤖 Analysis by {st.session_state.current_model}</span>', unsafe_allow_html=True)
    st.subheader("🔍 정밀 문진")
    st.info("AI가 환자의 증상을 바탕으로 생성한 추가 질문입니다.")
    
    for i, q in enumerate(st.session_state.follow_up_questions):
        st.markdown(f'<div class="q-item">{i+1}. {q}</div>', unsafe_allow_html=True)
        st.session_state.responses[f"q_{i}"] = st.text_input(f"답변 {i+1}", key=f"ans_{i}")
    
    if st.button("✅ 심층 진단 및 처방 생성"):
        st.session_state.step = "result"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

elif st.session_state.step == "result":
    if not st.session_state.final_plan:
        with st.spinner("데이터베이스를 대조하여 최적의 치료 혈자리를 선정 중입니다..."):
            p = st.session_state.patient_info
            age = calculate_age(p['birth_year'])
            ans_str = "\n".join([f"Q: {q}\nA: {st.session_state.responses.get(f'q_{i}', '내용 없음')}" for i, q in enumerate(st.session_state.follow_up_questions)])
            
            # DB 로드 (기본값 처리)
            if treatment_db_content:
                db_context = str(treatment_db_content)
            else:
                db_context = "치료 DB가 로드되지 않았습니다."

            FINAL_PROMPT = f"""
            [치료 DB]:
            {db_context}
            
            환자정보: {p['name']}({p['gender']}, {age}세)
            주소증: {st.session_state.raw_text}
            추가문진결과: {ans_str}

            [작성 지침 - 엄격 준수]:
            1. **[질환 분석]**: 양방/한방 질환명과 추론 근거.
            2. **[SOAP 차트]**: S/O/A/P 형식 (허위 정보 금지).
            3. **[원인 분석]**: 육기 이론에 근거한 원인.
            4. **[처방]**: 
               - DB에 있는 혈자리만 사용.
               - 형식: '혈자리명(코드) / 취혈방향(동측/대측) : 이유'
            5. **[생활 지도]**: 생활 습관 교정.
            
            ---
            (시스템 처리용: 맨 마지막에 `[이미지: URL]` 태그가 포함된 리스트를 나열하세요)
            """
            
            try:
                st.session_state.final_plan = analyze_with_hybrid_fallback(FINAL_PROMPT)
                
                # 구글 시트 저장
                new_id = str(uuid.uuid4())[:8]
                sheet = get_storage_sheet()
                if sheet:
                    # 이미지 태그 제거 후 저장
                    clean_content = re.sub(r'\[이미지:.*?\]', '', st.session_state.final_plan)
                    sheet.append_row([new_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), f"{p['name']}", "자동", clean_content])
                    st.session_state.shared_link = f"{MY_APP_URL}?view={new_id}"
            
            except Exception as e:
                st.error(f"최종 분석 실패: {e}")

    st.markdown('<div class="stCard">', unsafe_allow_html=True)
    if st.session_state.current_model:
        st.markdown(f'<span class="model-tag">🤖 Final Report by {st.session_state.current_model}</span>', unsafe_allow_html=True)
    
    st.subheader(f"📋 {st.session_state.patient_info['name']}님 최종진단")
    
    # 결과 출력 (마크다운 + 이미지 렌더링)
    if st.session_state.final_plan:
        raw_plan = st.session_state.final_plan.replace("```html", "").replace("```", "")
        # 본문에서 이미지 링크 텍스트 숨기기 (깔끔하게)
        display_text = re.sub(r'\[이미지:.*?\]', '', raw_plan)
        st.markdown(display_text)
        
        # 이미지 하단 배치
        img_patterns = re.findall(r'(\S+)\s*\[이미지:\s*(https?:\/\/[^\s\]]+)\]', raw_plan)
        if img_patterns:
            st.divider()
            st.markdown("##### 🖼️ 혈자리 가이드")
            cols = st.columns(2)
            for idx, (name, url) in enumerate(img_patterns):
                with cols[idx % 2]:
                    st.image(url.strip(), caption=name, use_container_width=True)

    if st.session_state.shared_link:
        st.divider()
        st.markdown("### 🔗 환자용 공유 링크")
        st.code(st.session_state.shared_link, language=None)
        
        # 카카오톡 전송 버튼
        kakao_js_key = st.secrets.get("JAVASCRIPT_KEY", "")
        patient_name = st.session_state.patient_info['name']
        
        kakao_button_html = f"""
        <script src="https://t1.kakaocdn.net/kakao_js_sdk/2.7.0/kakao.min.js"></script>
        <script>
            try {{
                if (!Kakao.isInitialized()) {{
                    Kakao.init('{kakao_js_key}');
                }}
            }} catch(e) {{ console.log(e); }}
            
            function sendToKakao() {{
                Kakao.Share.sendDefault({{
                    objectType: 'text',
                    text: '[한방 임상 보조 시스템]\\n{patient_name}님 진료 결과입니다.',
                    link: {{
                        mobileWebUrl: '{st.session_state.shared_link}',
                        webUrl: '{st.session_state.shared_link}',
                    }},
                }});
            }}
        </script>
        <div style="display: flex; justify-content: center; margin-top: 10px;">
            <button onclick="sendToKakao()" style="
                background-color: #FEE500; color: #191919; border: none; border-radius: 12px;
                padding: 15px 25px; font-size: 16px; font-weight: bold; cursor: pointer;
                display: flex; align-items: center; gap: 8px; width: 100%; justify-content: center;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            ">
                <img src="https://developers.kakao.com/assets/img/about/logos/kakaotalksharing/kakaotalk_sharing_btn_medium.png" width="24" height="24">
                내 카톡에 전송 / 환자에게 공유
            </button>
        </div>
        """
        components.html(kakao_button_html, height=80)

    st.divider()
    if st.button("🔄 다음 환자 진료 시작 (초기화)"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

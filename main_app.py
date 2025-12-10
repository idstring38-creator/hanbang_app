import streamlit as st
import streamlit.components.v1 as components

# --- Streamlit 기본 설정 ---
st.set_page_config(page_title="한의사 보조 앱", layout="wide")

st.title("🩺 한의사 임상 보조 시스템 (베타)")

menu = st.sidebar.selectbox(
    "메뉴 선택",
    ["1) 음성 → 텍스트", "2) 차트 자동 정리", "3) 치료법 검색"]
)

if menu == "1) 음성 → 텍스트":
    st.header("🎙 실시간 음성 → 텍스트 변환 (Web Speech API)")
    st.write("버튼을 눌러 말하면 텍스트가 실시간으로 입력됩니다. **(자동 끊김 방지 로직 적용)**")

    # --- JavaScript: Web Speech API (끊김 방지 로직 추가) ---
    speech_to_text = """
    <script>
    let recognizing = false;
    let globalRecognition;
    let finalTranscript = "";
    let autoRestartAttempt = false; // 자동 재시작 플래그

    function startRecognition() {
        window.SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        
        if (!globalRecognition) {
            globalRecognition = new window.SpeechRecognition();
            globalRecognition.continuous = true;
            globalRecognition.interimResults = true;
            globalRecognition.lang = "ko-KR";

            globalRecognition.onstart = () => {
                recognizing = true;
                autoRestartAttempt = false; // 시작할 때 초기화
                const btn = document.getElementById("recBtn");
                btn.innerText = "🎙️ 듣는 중... (말하세요)";
                btn.style.backgroundColor = "#ff5555";
            };

            globalRecognition.onerror = (event) => {
                console.log("Error:", event);
                
                // 에러 발생 시 자동 재시작 로직 실행
                if (event.error !== 'aborted') { // 사용자가 멈춘 것이 아닌 경우
                    if (!autoRestartAttempt) {
                        autoRestartAttempt = true;
                        setTimeout(() => {
                            if (!recognizing) {
                                globalRecognition.start(); 
                            }
                        }, 1000); // 1초 후 재시작 시도
                    }
                }
            };

            globalRecognition.onresult = (event) => {
                let interim = "";

                for (let i = event.resultIndex; i < event.results.length; ++i) {
                    if (event.results[i].isFinal) {
                        finalTranscript += event.results[i][0].transcript;
                    } else {
                        interim += event.results[i][0].transcript;
                    }
                }

                const textArea = document.getElementById("speechText");
                textArea.value = finalTranscript + " " + interim;

                // Streamlit에 값 전달 (Streamlit 텍스트 영역에 결과가 표시되도록)
                const inputEvent = new Event("input", { bubbles: true });
                textArea.dispatchEvent(inputEvent);
                
                // 결과가 들어왔으므로 재시작 플래그 초기화
                autoRestartAttempt = false;
            };

            globalRecognition.onend = () => {
                // 사용자가 멈춘 상태가 아니라면 (recognizing이 true였는데 onend가 호출됐다면)
                if (recognizing) { 
                    // 인식을 멈추지 않고, 자동으로 재시작을 시도합니다.
                    if (!autoRestartAttempt) {
                        autoRestartAttempt = true;
                        setTimeout(() => {
                            globalRecognition.start();
                        }, 500); // 0.5초 후 재시작 시도
                        return; // onend 로직 종료, 재시작 루프로 들어감
                    }
                }
                
                // 사용자가 버튼을 눌러 명시적으로 멈췄을 때만 실행
                recognizing = false;
                autoRestartAttempt = false;
                const btn = document.getElementById("recBtn");
                btn.innerText = "🎤 말하기 시작";
                btn.style.backgroundColor = "#4CAF50";
            };
        }

        if (!recognizing) {
            // 새로 시작할 때는 기존 내용 유지
            // finalTranscript = ""; 
            globalRecognition.start();
        } else {
            // 사용자가 명시적으로 멈출 때
            recognizing = false; // onend에서 자동 재시작을 막기 위해 false로 설정
            globalRecognition.stop();
        }
    }
    </script>

    <button id="recBtn" onclick="startRecognition()" 
    style="
        padding: 12px 20px;
        background-color: #4CAF50;
        color: white;
        border: none;
        font-size: 18px;
        border-radius: 8px;
        cursor: pointer;
    ">
    🎤 말하기 시작
    </button>

    <textarea id="speechText"
    style="width: 100%; height: 180px; margin-top: 20px; font-size: 16px;"></textarea>
    """

    components.html(speech_to_text, height=360)

    st.subheader("🔎 인식 결과")
    st.text_area("음성이 자동으로 입력됩니다:", key="speech_result", height=180)


elif menu == "2) 차트 자동 정리":
    st.header("📝 차트 자동 정리")
    st.info("이 기능은 **GPT-3.5 Turbo (유료)** 또는 **무료 오픈소스 LLM**을 사용해야 효율적입니다.")
    st.write("무료로 사용하시려면, 나중에 다른 **무료 AI API (예: 허깅페이스 모델)**를 연동하거나, 직접 정리하는 로직을 Python으로 짜야 합니다.")
    
    text = st.text_area("대화 원문 입력")
    
    if st.button("정리하기"):
        st.success("정리된 차트 예시 (자동 정리 로직 구현 필요):")
        st.write("CC: ...\nHPI: ...\nA: ...\nP: ...")

elif menu == "3) 치료법 검색":
    st.header("📚 치료법 검색")
    st.write("준비하신 치료법 DB(SQLite, CSV 등)에서 증상을 검색합니다. 이 기능은 순수 Python으로 구현 가능합니다.")
    keyword = st.text_input("증상/키워드 입력")

    if st.button("검색"):
        st.info(f"'{keyword}' 관련 치료법이 여기에 표시됩니다. (DB 검색 로직 구현 필요)")
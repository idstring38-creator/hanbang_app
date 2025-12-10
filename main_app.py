import streamlit as st

st.set_page_config(page_title="한의사 보조 앱", layout="wide")

st.title("🩺 한의사 임상 보조 시스템 (베타)")

menu = st.sidebar.selectbox(
    "메뉴 선택",
    ["1) 음성 → 텍스트", "2) 차트 자동 정리", "3) 치료법 검색"]
)

if menu == "1) 음성 → 텍스트":
    st.header("🎙 음성 인식 (기초 버전)")
    st.write("여기에 나중에 마이크 인식 기능을 붙일 거예요.")

elif menu == "2) 차트 자동 정리":
    st.header("📝 차트 자동 정리")
    text = st.text_area("대화 원문 입력")
    
    if st.button("정리하기"):
        st.success("정리된 차트 예시:")
        st.write("CC: ...\nHPI: ...\nA: ...\nP: ...")

elif menu == "3) 치료법 검색":
    st.header("📚 치료법 검색")
    keyword = st.text_input("증상/키워드 입력")

    if st.button("검색"):
        st.info(f"'{keyword}' 관련 치료법이 여기에 표시됩니다.")

import streamlit as st
import streamlit.components.v1 as components

st.title("🎤 실시간 음성 → 텍스트 변환 (Web Speech API)")

st.write("아래 버튼을 눌러 말하면 텍스트가 실시간으로 입력됩니다.")

# JavaScript: Web Speech API
speech_to_text = """
<script>
let recognizing = false;
let globalRecognition;
let finalTranscript = "";

function startRecognition() {
    window.SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    
    if (!globalRecognition) {
        globalRecognition = new window.SpeechRecognition();
        globalRecognition.continuous = true;
        globalRecognition.interimResults = true;
        globalRecognition.lang = "ko-KR";

        globalRecognition.onstart = () => {
            recognizing = true;
            const btn = document.getElementById("recBtn");
            btn.innerText = "🎙️ 듣는 중... (말하세요)";
            btn.style.backgroundColor = "#ff5555";
        };

        globalRecognition.onerror = (event) => {
            console.log("Error:", event);
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

            // Streamlit에 값 전달
            const inputEvent = new Event("input", { bubbles: true });
            textArea.dispatchEvent(inputEvent);
        };

        globalRecognition.onend = () => {
            recognizing = false;
            const btn = document.getElementById("recBtn");
            btn.innerText = "🎤 말하기 시작";
            btn.style.backgroundColor = "#4CAF50";
        };
    }

    if (!recognizing) {
        finalTranscript = "";
        globalRecognition.start();
    } else {
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

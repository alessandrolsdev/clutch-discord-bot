import streamlit as st
import requests
import threading
import socket
import pyaudio
import time
from streamlit.runtime.scriptrunner import add_script_run_ctx
from pedalboard import Pedalboard, PitchShift, Reverb, Distortion, Delay, HighpassFilter
from pedalboard.io import AudioFile

st.set_page_config(page_title="Clutch Voice Changer", page_icon="🎭", layout="wide")

# --- SELETOR DE AGENTE ---
st.sidebar.header("👥 Operador")
agente = st.sidebar.selectbox("Agente", ["Agente 01 (Alpha)", "Agente 02 (Bravo)"])

if agente == "Agente 01 (Alpha)":
    API_URL = "http://localhost:8080"
    UDP_PORT = 6001
    COLOR = "#00ff41"
    BG = "#002200"
else:
    API_URL = "http://localhost:8081"
    UDP_PORT = 6002
    COLOR = "#00bfff"
    BG = "#002244"

UDP_IP = "127.0.0.1"

# --- CSS TÁTICO ---
st.markdown(
    f"""
<style>
    .stApp {{background-color: #050505; color: {COLOR}; font-family: monospace;}}
    .status-bar {{padding: 10px; text-align: center; border: 1px solid {COLOR}; background: {BG}; font-weight: bold; margin-bottom: 20px;}}
    .stButton>button {{border: 1px solid {COLOR}; color: {COLOR}; background: #111; width: 100%;}}
    .stButton>button:hover {{background: {BG}; color: #fff;}}
</style>
""",
    unsafe_allow_html=True,
)

# Session State
if "transmitting" not in st.session_state:
    st.session_state.transmitting = False
if "effect" not in st.session_state:
    st.session_state.effect = "Normal"


# --- PROCESSADOR DE ÁUDIO ESTÚDIO (Pedalboard) ---
def aplicar_efeito(data_bytes, efeito):
    # Converte bytes brutos (int16) para float32 (padrão de estúdio -1.0 a 1.0)
    # O áudio do Discord é 48000Hz
    audio_int16 = np.frombuffer(data_bytes, dtype=np.int16)
    audio_float32 = audio_int16.astype(np.float32) / 32768.0

    # Pedalboard espera canais separados (Left/Right)
    # Como seu stream é estéreo (2 canais), precisamos remodelar
    audio_input = audio_float32.reshape(2, -1)  # [[L...], [R...]]

    board = Pedalboard([])

    if efeito == "👧 Voz Feminina / Criança":
        # Sobe o tom em 4 semitons (sem perder duração)
        board.append(PitchShift(semitones=4))

    elif efeito == "👹 Monstro Pro":
        # Desce o tom e adiciona distorção e ressonância
        board.append(PitchShift(semitones=-6))
        board.append(Distortion(drive_db=10))
        board.append(Reverb(room_size=0.8))  # Caverna

    elif efeito == "📻 Rádio Velho":
        # Corta graves e agudos + Distorção leve
        board.append(HighpassFilter(cutoff_frequency_hz=1000))
        board.append(Distortion(drive_db=20))

    elif efeito == "⛪ Catedral":
        # Apenas um Reverb gigante
        board.append(Reverb(room_size=1.0, wet_level=0.5))

    # Processa o áudio (A mágica acontece aqui)
    try:
        processed = board(audio_input, 48000)

        # Converte de volta para int16 para enviar pro Discord
        # O clip garante que não estoure o áudio (> 1.0)
        processed = np.clip(processed, -1.0, 1.0)
        audio_output = (processed * 32767.0).astype(np.int16)

        # Transforma em bytes novamente (intercalando L/R para stream)
        # O Pedalboard devolve [[L...], [R...]], precisamos juntar LRLRLR
        audio_output = audio_output.flatten(
            "F"
        )  # Flatten Fortran style intercala corretamente 2 canais
        return audio_output.tobytes()

    except Exception as e:
        print(f"Erro DSP: {e}")
        return data_bytes


# --- THREAD DO MICROFONE ---
def thread_mic():
    p = pyaudio.PyAudio()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # IMPORTANTE: Buffer menor para menos latência nos efeitos
    CHUNK = 960

    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=2,
            rate=48000,
            input=True,
            frames_per_buffer=CHUNK,
        )

        while st.session_state.transmitting:
            try:
                raw_data = stream.read(CHUNK, exception_on_overflow=False)

                # APLICA O EFEITO SELECIONADO NA UI
                processed_data = aplicar_efeito(raw_data, st.session_state.effect)

                sock.sendto(processed_data, (UDP_IP, UDP_PORT))
            except:
                pass
    except:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
        sock.close()


# --- LOOP DE DADOS ---
try:
    r = requests.get(f"{API_URL}/status", timeout=0.1).json()
    status, canal = "ONLINE", r.get("channel", "---")
except:
    status, canal = "OFFLINE", "---"

# --- SIDEBAR (CONTROLES) ---
with st.sidebar:
    st.header("🎭 Modulador de Voz")

    # SELETOR DE EFEITO (Salva no Session State para a Thread ler)
    selected_effect = st.selectbox(
        "Escolha seu Disfarce:",
        ["Normal", "🤖 Robô", "🐿️ Esquilo", "👹 Monstro", "👽 Alien"],
    )
    st.session_state.effect = selected_effect  # Atualiza globalmente

    st.markdown("---")
    st.subheader("📡 Conexão")
    channel_id = st.text_input("ID Voz", key="chan_id")
    c1, c2 = st.columns(2)
    if c1.button("INFILTRAR"):
        requests.post(f"{API_URL}/connect", json={"channel_id": channel_id})
        st.rerun()
    if c2.button("SAIR"):
        requests.post(f"{API_URL}/disconnect")
        st.rerun()

# --- ÁREA PRINCIPAL ---
icon_efeito = "🗣️"
if st.session_state.effect == "🤖 Robô":
    icon_efeito = "🤖"
elif st.session_state.effect == "👹 Monstro":
    icon_efeito = "👹"

st.markdown(
    f'<div class="status-bar">{icon_efeito} MODO ATUAL: {st.session_state.effect.upper()}</div>',
    unsafe_allow_html=True,
)

c_mic, c_info = st.columns([1, 2])

with c_mic:
    st.subheader("🎙️ Transmissão")
    if st.session_state.transmitting:
        st.error("🔴 NO AR")
        if st.button("CORTAR"):
            st.session_state.transmitting = False
            st.rerun()
    else:
        st.success("🟢 PRONTO")
        if st.button("ATIVAR MICROFONE"):
            st.session_state.transmitting = True

            t = threading.Thread(target=thread_mic, daemon=True)

            add_script_run_ctx(t)

            t.start()
            st.rerun()

with c_info:
    st.subheader("📊 Status")
    st.info(f"Conectado em: {canal}")
    st.text(f"Agente: {agente}")
    st.text(f"API: {API_URL}")

# Auto-refresh
time.sleep(1)
st.rerun()

import streamlit as st
import requests
import time
import socket
import pyaudio
import threading

# --- CONFIGURAÇÕES DO PAINEL ---
st.set_page_config(page_title="Clutch Spy Center", page_icon="🕵️‍♂️", layout="centered")
st.markdown("""
<style>
    .stApp {background-color: #0e1117; color: #00ff00; font-family: monospace;}
    .stButton>button {background-color: #004400; color: #00ff00; border: 1px solid #00ff00; width: 100%;}
    .stButton>button:hover {background-color: #006600;}
    div[data-testid="stMetricValue"] {color: #00ff00;}
    .big-status {font-size: 20px; font-weight: bold; padding: 10px; border-radius: 5px; text-align: center;}
    .status-on {background-color: #00aa00; color: black;}
    .status-off {background-color: #330000; color: #ff0000;}
</style>
""", unsafe_allow_html=True)

API_URL = "http://localhost:8080"
UDP_IP_DOCKER = "127.0.0.1" # Manda para o Docker
UDP_PORT_MIC = 6001

# --- ESTADO DO SISTEMA (SESSION STATE) ---
if 'transmitting' not in st.session_state:
    st.session_state.transmitting = False

# --- FUNÇÃO DE TRANSMISSÃO (RODA EM BACKGROUND) ---
def thread_microfone():
    """Lê o mic e manda via UDP enquanto o botão estiver ligado"""
    p = pyaudio.PyAudio()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        # Configuração igual ao Discord
        stream = p.open(format=pyaudio.paInt16, channels=2, rate=48000, input=True, frames_per_buffer=960)
        
        while st.session_state.transmitting:
            try:
                data = stream.read(960, exception_on_overflow=False)
                sock.sendto(data, (UDP_IP_DOCKER, UDP_PORT_MIC))
            except:
                pass
                
    except Exception as e:
        print(f"Erro Mic: {e}")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
        sock.close()

# --- INTERFACE GRÁFICA ---

st.title("🛰️ CLUTCH COMMAND CENTER")

# 1. STATUS DO BOT
try:
    r = requests.get(f"{API_URL}/status", timeout=0.5)
    data = r.json()
    status_bot = "🟢 ONLINE"
    canal_atual = data.get('voice_channel', '---')
except:
    status_bot = "🔴 OFFLINE"
    canal_atual = "---"

c1, c2, c3 = st.columns(3)
c1.metric("Bot Link", status_bot)
c2.metric("Alvo", canal_atual)

# Indicador Visual de Transmissão
if st.session_state.transmitting:
    c3.markdown('<div class="big-status status-on">🎙️ NO AR</div>', unsafe_allow_html=True)
else:
    c3.markdown('<div class="big-status status-off">🔇 MUDO</div>', unsafe_allow_html=True)

st.divider()

# 2. CONTROLE DE CONEXÃO
st.subheader("📡 Invasão de Frequência")
channel_id = st.text_input("ID do Canal", placeholder="Cole o ID aqui...")

col_inv1, col_inv2 = st.columns(2)
if col_inv1.button("🚀 INFILTRAR"):
    try:
        r = requests.post(f"{API_URL}/connect", json={'channel_id': channel_id})
        st.success(r.json()['message'])
        time.sleep(1)
        st.rerun()
    except Exception as e: st.error(f"Erro: {e}")

if col_inv2.button("⏹️ ABORTAR"):
    try:
        requests.post(f"{API_URL}/disconnect")
        st.warning("Desconectado.")
        time.sleep(1)
        st.rerun()
    except: pass

st.divider()

# 3. CONTROLE DO RÁDIO (NOVO!)
st.subheader("🎙️ Transmissão de Voz (Walkie-Talkie)")

col_mic1, col_mic2 = st.columns(2)

# Botão LIGAR
if col_mic1.button("🔴 ABRIR MICROFONE"):
    if not st.session_state.transmitting:
        st.session_state.transmitting = True
        # Inicia a thread separada para não travar o site
        t = threading.Thread(target=thread_microfone, daemon=True)
        t.start()
        st.rerun()

# Botão DESLIGAR
if col_mic2.button("🤐 CORTAR TRANSMISSÃO"):
    if st.session_state.transmitting:
        st.session_state.transmitting = False
        st.rerun()

st.caption("🔒 CLUTCH SYSTEMS V3.0 - DUAL AUDIO LINK ESTABLISHED")
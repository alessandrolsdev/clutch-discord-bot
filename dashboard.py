"""
CLUTCH BOT - DASHBOARD PREMIUM V3.0
====================================

Interface de controle visual premium com design moderno nível Awwwards.

Recursos:
- 🎨 Glassmorphism e gradientes modernos
- 🎭 16 efeitos de voz profissionais
- 📊 Visualizador de áudio em tempo real
- 🎛️ Controles de volume individual
- 🔊 Soundboard integrado
- 📡 Status em tempo real
- ⚡ Animações fluidas

Autor: Clutch Development Team
Versão: 3.0 Premium
"""

import streamlit as st
import requests
import threading
import socket
import time
import numpy as np
from streamlit.runtime.scriptrunner import add_script_run_ctx

# Importações condicionais (PyAudio é opcional)
try:
    import pyaudio

    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False

try:
    from pedalboard import (
        Pedalboard,
        PitchShift,
        Reverb,
        Distortion,
        Delay,
        HighpassFilter,
        Chorus,
        Phaser,
        Compressor,
    )

    PEDALBOARD_AVAILABLE = True
except ImportError:
    PEDALBOARD_AVAILABLE = False

# ============================================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================================

st.set_page_config(
    page_title="Clutch Control Center",
    page_icon="🎛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# ESTILOS CSS PREMIUM (Nível Awwwards)
# ============================================================================

st.markdown(
    """
<style>
    /* === RESET E BASE === */
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }
    
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
    
    /* === VARIÁVEIS CSS === */
    :root {
        --primary: #00D9FF;
        --primary-dark: #0099CC;
        --secondary: #7B2CBF;
        --accent: #FF006E;
        --success: #06FFA5;
        --warning: #FFB800;
        --danger: #FF3D71;
        
        --glass-bg: rgba(20, 20, 35, 0.7);
        --glass-border: rgba(255, 255, 255, 0.1);
        
        --gradient-1: linear-gradient(135deg, #00D9FF 0%, #7B2CBF 100%);
        --gradient-2: linear-gradient(135deg, #FF006E 0%, #FFB800 100%);
        --gradient-3: linear-gradient(135deg, #06FFA5 0%, #00D9FF 100%);
    }
    
    /* === BACKGROUND ANIMADO === */
    .stApp {
        background: #0A0E1A;
        background-image: 
            radial-gradient(at 0% 0%, rgba(0, 217, 255, 0.1) 0px, transparent 50%),
            radial-gradient(at 100% 0%, rgba(123, 44, 191, 0.1) 0px, transparent 50%),
            radial-gradient(at 100% 100%, rgba(255, 0, 110, 0.1) 0px, transparent 50%),
            radial-gradient(at 0% 100%, rgba(6, 255, 165, 0.1) 0px, transparent 50%);
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        color: #E8E8F0;
    }
    
    /* === HEADER PREMIUM === */
    .main-header {
        background: var(--glass-bg);
        backdrop-filter: blur(20px);
        border: 1px solid var(--glass-border);
        border-radius: 24px;
        padding: 32px 40px;
        margin-bottom: 32px;
        position: relative;
        overflow: hidden;
    }
    
    .main-header::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: var(--gradient-1);
    }
    
    .main-header h1 {
        font-size: 48px;
        font-weight: 900;
        background: var(--gradient-1);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
        letter-spacing: -1px;
    }
    
    .main-header p {
        color: rgba(255, 255, 255, 0.6);
        font-size: 16px;
        margin-top: 8px;
        font-weight: 400;
    }
    
    /* === GLASS CARDS === */
    .glass-card {
        background: var(--glass-bg);
        backdrop-filter: blur(20px);
        border: 1px solid var(--glass-border);
        border-radius: 20px;
        padding: 24px;
        margin-bottom: 20px;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    .glass-card:hover {
        border-color: rgba(0, 217, 255, 0.3);
        transform: translateY(-2px);
        box-shadow: 0 20px 60px rgba(0, 217, 255, 0.1);
    }
    
    /* === BOTÕES PREMIUM === */
    .stButton > button {
        background: var(--gradient-1);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 14px 28px;
        font-weight: 600;
        font-size: 15px;
        letter-spacing: 0.5px;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 4px 20px rgba(0, 217, 255, 0.3);
        width: 100%;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 30px rgba(0, 217, 255, 0.5);
    }
    
    .stButton > button:active {
        transform: translateY(0px);
    }
    
    /* === SELECT BOX PREMIUM === */
    .stSelectbox > div > div {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid var(--glass-border);
        border-radius: 12px;
        color: white;
        transition: all 0.3s ease;
    }
    
    .stSelectbox > div > div:hover {
        border-color: var(--primary);
        background: rgba(255, 255, 255, 0.08);
    }
    
    /* === INPUT FIELDS === */
    .stTextInput > div > div > input {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid var(--glass-border);
        border-radius: 12px;
        color: white;
        padding: 12px 16px;
        font-size: 15px;
        transition: all 0.3s ease;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: var(--primary);
        background: rgba(255, 255, 255, 0.08);
        box-shadow: 0 0 0 3px rgba(0, 217, 255, 0.1);
    }
    
    /* === SLIDER PREMIUM === */
    .stSlider > div > div > div {
        background: var(--gradient-1);
    }
    
    /* === STATUS BADGES === */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px 16px;
        border-radius: 100px;
        font-size: 13px;
        font-weight: 600;
        letter-spacing: 0.5px;
        text-transform: uppercase;
    }
    
    .status-online {
        background: rgba(6, 255, 165, 0.15);
        color: var(--success);
        border: 1px solid rgba(6, 255, 165, 0.3);
    }
    
    .status-offline {
        background: rgba(255, 61, 113, 0.15);
        color: var(--danger);
        border: 1px solid rgba(255, 61, 113, 0.3);
    }
    
    .status-transmitting {
        background: rgba(255, 184, 0, 0.15);
        color: var(--warning);
        border: 1px solid rgba(255, 184, 0, 0.3);
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.6; }
    }
    
    /* === AUDIO VISUALIZER === */
    .visualizer-container {
        display: flex;
        align-items: flex-end;
        justify-content: space-around;
        height: 100px;
        gap: 4px;
        padding: 20px;
        background: rgba(0, 217, 255, 0.05);
        border-radius: 16px;
        border: 1px solid rgba(0, 217, 255, 0.1);
    }
    
    .visualizer-bar {
        flex: 1;
        background: var(--gradient-1);
        border-radius: 4px 4px 0 0;
        animation: visualizer 0.3s ease infinite;
        min-height: 4px;
    }
    
    @keyframes visualizer {
        0%, 100% { transform: scaleY(1); }
        50% { transform: scaleY(0.5); }
    }
    
    /* === EFFECT CARDS === */
    .effect-card {
        background: var(--glass-bg);
        border: 2px solid transparent;
        border-radius: 16px;
        padding: 20px;
        text-align: center;
        cursor: pointer;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    
    .effect-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: var(--gradient-1);
        opacity: 0;
        transition: opacity 0.3s ease;
    }
    
    .effect-card:hover {
        border-color: var(--primary);
        transform: translateY(-4px);
        box-shadow: 0 12px 40px rgba(0, 217, 255, 0.2);
    }
    
    .effect-card:hover::before {
        opacity: 0.1;
    }
    
    .effect-card.active {
        border-color: var(--success);
        background: rgba(6, 255, 165, 0.1);
    }
    
    /* === SIDEBAR MODERN === */
    [data-testid="stSidebar"] {
        background: rgba(10, 14, 26, 0.95);
        backdrop-filter: blur(20px);
        border-right: 1px solid var(--glass-border);
    }
    
    [data-testid="stSidebar"] > div {
        padding-top: 40px;
    }
    
    /* === MÉTRICAS === */
    .metric-card {
        background: var(--glass-bg);
        backdrop-filter: blur(20px);
        border: 1px solid var(--glass-border);
        border-radius: 16px;
        padding: 20px;
        text-align: center;
    }
    
    .metric-value {
        font-size: 32px;
        font-weight: 800;
        background: var(--gradient-1);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    .metric-label {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: rgba(255, 255, 255, 0.5);
        margin-top: 4px;
    }
    
    /* === SCROLLBAR CUSTOM === */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: rgba(255, 255, 255, 0.05);
    }
    
    ::-webkit-scrollbar-thumb {
        background: var(--gradient-1);
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: var(--primary-dark);
    }
    
    /* === REMOVE STREAMLIT BRANDING === */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================================
# EFEITOS DE VOZ PROFISSIONAIS
# ============================================================================

VOICE_EFFECTS = {
    "Normal": {
        "icon": "🎤",
        "name": "Normal",
        "description": "Sem processamento",
        "color": "#E8E8F0",
    },
    "Robot": {
        "icon": "🤖",
        "name": "Robô",
        "description": "Voz robótica clássica",
        "pedalboard": lambda: [
            PitchShift(semitones=0),
            Chorus(rate_hz=1.5, depth=0.5, mix=0.7),
        ],
    },
    "Chipmunk": {
        "icon": "🐿️",
        "name": "Esquilo",
        "description": "Voz aguda e rápida",
        "pedalboard": lambda: [PitchShift(semitones=8)],
    },
    "Monster": {
        "icon": "👹",
        "name": "Monstro",
        "description": "Voz grave e assustadora",
        "pedalboard": lambda: [
            PitchShift(semitones=-8),
            Distortion(drive_db=15),
            Reverb(room_size=0.9),
        ],
    },
    "Alien": {
        "icon": "👽",
        "name": "Alienígena",
        "description": "Voz extraterrestre",
        "pedalboard": lambda: [
            PitchShift(semitones=3),
            Phaser(rate_hz=0.5, depth=0.8),
            Delay(delay_seconds=0.1, mix=0.3),
        ],
    },
    "Female": {
        "icon": "👧",
        "name": "Voz Feminina",
        "description": "Tom mais agudo",
        "pedalboard": lambda: [PitchShift(semitones=4)],
    },
    "Monster_Pro": {
        "icon": "😈",
        "name": "Demônio",
        "description": "Monstro profissional",
        "pedalboard": lambda: [
            PitchShift(semitones=-12),
            Distortion(drive_db=20),
            Reverb(room_size=1.0, wet_level=0.6),
        ],
    },
    "Radio": {
        "icon": "📻",
        "name": "Rádio Antigo",
        "description": "Som de transmissão vintage",
        "pedalboard": lambda: [
            HighpassFilter(cutoff_frequency_hz=800),
            Distortion(drive_db=18),
            Compressor(threshold_db=-10),
        ],
    },
    "Cathedral": {
        "icon": "⛪",
        "name": "Catedral",
        "description": "Reverb gigante",
        "pedalboard": lambda: [Reverb(room_size=1.0, wet_level=0.7)],
    },
    "Cave": {
        "icon": "🕳️",
        "name": "Caverna",
        "description": "Eco profundo",
        "pedalboard": lambda: [
            Reverb(room_size=0.95, wet_level=0.5),
            Delay(delay_seconds=0.2, mix=0.4),
        ],
    },
    "Underwater": {
        "icon": "🌊",
        "name": "Subaquático",
        "description": "Som abafado",
        "pedalboard": lambda: [
            HighpassFilter(cutoff_frequency_hz=300),
            Chorus(rate_hz=0.3, depth=0.7),
            Reverb(room_size=0.7, wet_level=0.5),
        ],
    },
    "Telephone": {
        "icon": "📞",
        "name": "Telefone",
        "description": "Qualidade de ligação",
        "pedalboard": lambda: [
            HighpassFilter(cutoff_frequency_hz=1200),
            Distortion(drive_db=12),
            Compressor(threshold_db=-15),
        ],
    },
    "Megaphone": {
        "icon": "📢",
        "name": "Megafone",
        "description": "Distorção de alto-falante",
        "pedalboard": lambda: [
            Distortion(drive_db=25),
            HighpassFilter(cutoff_frequency_hz=600),
            Compressor(threshold_db=-8),
        ],
    },
    "Space": {
        "icon": "🚀",
        "name": "Espacial",
        "description": "Som de astronauta",
        "pedalboard": lambda: [
            PitchShift(semitones=-2),
            Phaser(rate_hz=0.7, depth=0.9),
            Reverb(room_size=1.0, wet_level=0.4),
            Delay(delay_seconds=0.15, mix=0.3),
        ],
    },
    "Chorus": {
        "icon": "🎶",
        "name": "Coro",
        "description": "Múltiplas vozes",
        "pedalboard": lambda: [Chorus(rate_hz=2.0, depth=0.8, mix=0.9)],
    },
    "Vibrato": {
        "icon": "〰️",
        "name": "Vibrato",
        "description": "Oscilação de pitch",
        "pedalboard": lambda: [Chorus(rate_hz=5.0, depth=0.3, mix=0.5)],
    },
}

# ============================================================================
# ESTADO DA SESSÃO
# ============================================================================

if "transmitting" not in st.session_state:
    st.session_state.transmitting = False

if "current_effect" not in st.session_state:
    st.session_state.current_effect = "Normal"

if "volume_mic" not in st.session_state:
    st.session_state.volume_mic = 0.7

if "volume_fx" not in st.session_state:
    st.session_state.volume_fx = 1.0

if "agent" not in st.session_state:
    st.session_state.agent = "Alpha"

# ============================================================================
# CONFIGURAÇÕES DE AGENTE
# ============================================================================

if st.session_state.agent == "Alpha":
    API_URL = "http://localhost:8080"
    UDP_PORT = 6001
    THEME_COLOR = "#00D9FF"
else:
    API_URL = "http://localhost:8081"
    UDP_PORT = 6002
    THEME_COLOR = "#FF006E"

UDP_IP = "127.0.0.1"

# ============================================================================
# PROCESSAMENTO DE ÁUDIO
# ============================================================================


def aplicar_efeito(data_bytes, efeito_nome):
    """Aplica efeito de voz ao áudio"""
    if not PEDALBOARD_AVAILABLE or efeito_nome == "Normal":
        return data_bytes

    try:
        # Converte bytes para float32
        audio_int16 = np.frombuffer(data_bytes, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        audio_input = audio_float32.reshape(2, -1)

        # Cria pedalboard com efeito
        effect_config = VOICE_EFFECTS.get(efeito_nome, {})
        if "pedalboard" in effect_config:
            board = Pedalboard(effect_config["pedalboard"]())
            processed = board(audio_input, 48000)

            # Converte de volta para int16
            processed = np.clip(processed, -1.0, 1.0)
            audio_output = (processed * 32767.0).astype(np.int16)
            audio_output = audio_output.flatten("F")
            return audio_output.tobytes()
    except Exception as e:
        print(f"Erro ao aplicar efeito: {e}")

    return data_bytes


def thread_mic():
    """Thread de captura do microfone"""
    if not PYAUDIO_AVAILABLE:
        return

    p = pyaudio.PyAudio()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
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
                processed_data = aplicar_efeito(
                    raw_data, st.session_state.current_effect
                )
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


# ============================================================================
# HEADER E LAYOUT PRINCIPAL
# ============================================================================

st.markdown(
    f"""
<div class="main-header">
    <h1>🎛️ Clutch Control Center</h1>
    <p>Interface Premium de Controle de Áudio v3.0</p>
</div>
""",
    unsafe_allow_html=True,
)

# SIDEBAR
with st.sidebar:
    st.markdown("### 👤 Agente")
    agente_selecionado = st.radio(
        "Selecione o agente:",
        ["Alpha", "Bravo"],
        index=0 if st.session_state.agent == "Alpha" else 1,
        key="agent_selector",
    )
    st.session_state.agent = agente_selecionado

    st.markdown("---")

    # Status da API
    try:
        r = requests.get(f"{API_URL}/status", timeout=0.5).json()
        bot_status = "ONLINE"
        canal_atual = r.get("channel", "Desconectado")
    except:
        bot_status = "OFFLINE"
        canal_atual = "---"

    status_class = "status-online" if bot_status == "ONLINE" else "status-offline"
    st.markdown(
        f'<div class="glass-card"><div class="status-badge {status_class}">● {bot_status}</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown(f"**Canal:** {canal_atual}")

    st.markdown("---")

    st.markdown("### 📡 Conexão")
    channel_id = st.text_input("ID do Canal de Voz", key="channel_id_input")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔗 Conectar", use_container_width=True):
            if channel_id:
                try:
                    requests.post(
                        f"{API_URL}/connect", json={"channel_id": channel_id}, timeout=2
                    )
                    st.success("Conectando...")
                    time.sleep(1)
                    st.rerun()
                except:
                    st.error("Erro ao conectar")

    with col2:
        if st.button("❌ Desconectar", use_container_width=True):
            try:
                requests.post(f"{API_URL}/disconnect", timeout=2)
                st.success("Desconectado")
                time.sleep(1)
                st.rerun()
            except:
                pass

    st.markdown("---")

    # Volumes
    st.markdown("### 🎚️ Volumes")
    st.session_state.volume_mic = st.slider(
        "🎤 Microfone", 0.0, 1.0, st.session_state.volume_mic, 0.1
    )
    st.session_state.volume_fx = st.slider(
        "🔊 Efeitos", 0.0, 1.0, st.session_state.volume_fx, 0.1
    )

# ÁREA PRINCIPAL
tab_effects, tab_soundboard, tab_status = st.tabs(
    ["🎭 Efeitos de Voz", "🎵 Soundboard", "📊 Status"]
)

with tab_effects:
    # Controles de microfone
    col_mic1, col_mic2 = st.columns([1, 2])

    with col_mic1:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("### 🎙️ Transmissão")

        if st.session_state.transmitting:
            status_badge = (
                '<div class="status-badge status-transmitting">🔴 TRANSMITINDO</div>'
            )
            st.markdown(status_badge, unsafe_allow_html=True)

            if st.button("⏹️ Parar", use_container_width=True, type="primary"):
                st.session_state.transmitting = False
                st.rerun()
        else:
            status_badge = '<div class="status-badge status-online">🟢 PRONTO</div>'
            st.markdown(status_badge, unsafe_allow_html=True)

            if PYAUDIO_AVAILABLE:
                if st.button(
                    "▶️ Ativar Microfone", use_container_width=True, type="primary"
                ):
                    st.session_state.transmitting = True
                    t = threading.Thread(target=thread_mic, daemon=True)
                    add_script_run_ctx(t)
                    t.start()
                    st.rerun()
            else:
                st.warning("⚠️ PyAudio não instalado")

        st.markdown("</div>", unsafe_allow_html=True)

    with col_mic2:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("### 📊 Visualizador de Áudio")
        # Simulador de visualizador (você pode integrar com dados reais)
        bars_html = '<div class="visualizer-container">'
        for i in range(20):
            height = np.random.randint(20, 100)
            bars_html += (
                f'<div class="visualizer-bar" style="height: {height}px;"></div>'
            )
        bars_html += "</div>"
        st.markdown(bars_html, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # Grid de efeitos
    st.markdown("### 🎭 Selecione o Efeito de Voz")

    cols = st.columns(4)
    effects_list = list(VOICE_EFFECTS.keys())

    for idx, effect_key in enumerate(effects_list):
        effect = VOICE_EFFECTS[effect_key]
        col_idx = idx % 4

        with cols[col_idx]:
            active_class = (
                "active" if st.session_state.current_effect == effect_key else ""
            )

            if st.button(
                f"{effect['icon']}\n{effect['name']}",
                key=f"effect_{effect_key}",
                use_container_width=True,
                help=effect.get("description", ""),
            ):
                st.session_state.current_effect = effect_key
                st.rerun()

with tab_soundboard:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### 🎵 Soundboard")
    st.info("🚧 Soundboard em desenvolvimento - Em breve!")

    # Exemplo de layout futuro
    sound_cols = st.columns(3)
    example_sounds = [
        "🔔 Alarme",
        "📢 Buzina",
        "🎉 Comemoração",
        "😂 Risada",
        "👏 Palmas",
        "💥 Explosão",
    ]

    for idx, sound in enumerate(example_sounds):
        with sound_cols[idx % 3]:
            if st.button(sound, use_container_width=True):
                st.toast(f"Som {sound} em breve!")

    st.markdown("</div>", unsafe_allow_html=True)

with tab_status:
    st.markdown("### 📊 Status do Sistema")

    metric_cols = st.columns(4)

    with metric_cols[0]:
        st.markdown(
            """
        <div class="metric-card">
            <div class="metric-value">{}</div>
            <div class="metric-label">Bot Status</div>
        </div>
        """.format(
                bot_status
            ),
            unsafe_allow_html=True,
        )

    with metric_cols[1]:
        st.markdown(
            """
        <div class="metric-card">
            <div class="metric-value">{}</div>
            <div class="metric-label">Efeito Atual</div>
        </div>
        """.format(
                VOICE_EFFECTS[st.session_state.current_effect]["name"]
            ),
            unsafe_allow_html=True,
        )

    with metric_cols[2]:
        mic_status = "ON" if st.session_state.transmitting else "OFF"
        st.markdown(
            """
        <div class="metric-card">
            <div class="metric-value">{}</div>
            <div class="metric-label">Microfone</div>
        </div>
        """.format(
                mic_status
            ),
            unsafe_allow_html=True,
        )

    with metric_cols[3]:
        st.markdown(
            """
        <div class="metric-card">
            <div class="metric-value">{}</div>
            <div class="metric-label">Agente</div>
        </div>
        """.format(
                st.session_state.agent
            ),
            unsafe_allow_html=True,
        )

    st.markdown("---")

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### 🔧 Informações Técnicas")

    tech_col1, tech_col2 = st.columns(2)

    with tech_col1:
        st.markdown(
            f"""
        **API Endpoint:** `{API_URL}`  
        **UDP Port:** `{UDP_PORT}`  
        **Sample Rate:** `48000 Hz`  
        **Channels:** `2 (Stereo)`
        """
        )

    with tech_col2:
        st.markdown(
            f"""
        **PyAudio:** {'✅ Instalado' if PYAUDIO_AVAILABLE else '❌ Não instalado'}  
        **Pedalboard:** {'✅ Instalado' if PEDALBOARD_AVAILABLE else '❌ Não instalado'}  
        **Volume Mic:** `{int(st.session_state.volume_mic * 100)}%`  
        **Volume FX:** `{int(st.session_state.volume_fx * 100)}%`
        """
        )

    st.markdown("</div>", unsafe_allow_html=True)

# Auto-refresh a cada 2 segundos
time.sleep(2)
st.rerun()

"""
CLUTCH BOT - DASHBOARD PREMIUM V3.0
====================================

Interface de controle visual do bot.

Correções desta versão:
- Envia o header ``X-API-Key`` em todas as chamadas (a API agora autentica).
- Os sliders de volume realmente chamam ``POST /volume``; antes só mudavam um
  valor local que nunca saía do navegador.
- O soundboard usa a lista real de sons vinda de ``GET /status`` e dispara
  ``POST /play`` (antes era um placeholder "em desenvolvimento").
- Removido o ``time.sleep(2) + st.rerun()`` no fim do script, que criava um
  loop de recarga infinito consumindo CPU e reiniciando a página o tempo todo.
- A thread do microfone não lê mais ``st.session_state`` (proibido fora do
  script principal); ela é controlada por um objeto compartilhado com Event.
- ``aplicar_efeito`` desintercalava os canais de forma errada
  (``reshape(2, -1)`` em áudio intercalado), o que embaralhava o estéreo.

Uso:
    streamlit run dashboard.py
"""

import os
import socket
import threading
import time
from typing import Optional

import numpy as np
import requests
import streamlit as st

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
# ESTILOS CSS PREMIUM
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
        "name": "Voz Aguda",
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
# CONFIGURAÇÃO DE ÁUDIO E REDE
# ============================================================================

SAMPLE_RATE = 48000
CHANNELS = 2
CHUNK = 960  # 20ms — mesmo frame do Discord

# Configuração por agente (sobrescrevível por variáveis de ambiente)
AGENTES = {
    "Alpha": {
        "api_url": os.getenv("CLUTCH_API_URL_ALPHA", "http://127.0.0.1:8080"),
        "api_key": os.getenv("API_KEY_1", os.getenv("API_KEY", "")),
        "udp_port": int(os.getenv("UDP_PORT_ALPHA", "6001")),
    },
    "Bravo": {
        "api_url": os.getenv("CLUTCH_API_URL_BRAVO", "http://127.0.0.1:8081"),
        "api_key": os.getenv("API_KEY_2", os.getenv("API_KEY", "")),
        "udp_port": int(os.getenv("UDP_PORT_BRAVO", "6002")),
    },
}

UDP_IP = os.getenv("UDP_TARGET_IP", "127.0.0.1")

# Rótulos dos modos de repetição do player (espelham utils/musica_fila.LoopMode)
ROTULOS_LOOP = {
    "off": "➡️ Desligado",
    "track": "🔂 Faixa",
    "queue": "🔁 Fila",
}


def formatar_tempo(segundos: Optional[int]) -> str:
    """Formata segundos como MM:SS (ou ──:── quando não há duração)."""
    if not segundos or segundos < 0:
        return "──:──"

    segundos = int(segundos)
    horas, resto = divmod(segundos, 3600)
    minutos, segs = divmod(resto, 60)

    if horas:
        return f"{horas}:{minutos:02d}:{segs:02d}"
    return f"{minutos}:{segs:02d}"


# ============================================================================
# PROCESSAMENTO DE ÁUDIO
# ============================================================================


def aplicar_efeito(data_bytes: bytes, efeito_nome: str) -> bytes:
    """
    Aplica um efeito de voz a um bloco de PCM 16-bit estéreo intercalado.

    Args:
        data_bytes: Áudio bruto do microfone
        efeito_nome: Chave em VOICE_EFFECTS

    Returns:
        Áudio processado (ou o original se o efeito não se aplica)
    """
    if not PEDALBOARD_AVAILABLE or efeito_nome == "Normal":
        return data_bytes

    efeito = VOICE_EFFECTS.get(efeito_nome, {})
    if "pedalboard" not in efeito:
        return data_bytes

    try:
        # int16 intercalado -> float32 por canal, formato (canais, amostras)
        amostras = np.frombuffer(data_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if amostras.size % CHANNELS:
            amostras = amostras[: amostras.size - (amostras.size % CHANNELS)]

        entrada = amostras.reshape(-1, CHANNELS).T

        board = Pedalboard(efeito["pedalboard"]())
        processado = np.clip(board(entrada, SAMPLE_RATE), -1.0, 1.0)

        # Volta para int16 intercalado
        saida = (processado * 32767.0).astype(np.int16).T.reshape(-1)
        return saida.tobytes()
    except Exception as e:  # noqa: BLE001 - efeito não deve derrubar a captura
        print(f"Erro ao aplicar efeito {efeito_nome}: {e}")
        return data_bytes


class MicController:
    """
    Controla a thread de captura do microfone.

    A thread não pode ler ``st.session_state`` (Streamlit só permite isso no
    script principal), então efeito e destino ficam neste objeto compartilhado.
    """

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.effect = "Normal"
        self.target = (UDP_IP, 6001)
        self.last_error: Optional[str] = None

    def is_running(self) -> bool:
        """True se a captura está ativa."""
        return self._thread is not None and self._thread.is_alive()

    def set_effect(self, effect: str) -> None:
        """Troca o efeito aplicado em tempo real."""
        with self._lock:
            self.effect = effect

    def _current_effect(self) -> str:
        with self._lock:
            return self.effect

    def start(self, host: str, port: int, effect: str) -> None:
        """Inicia a captura enviando para host:port via UDP."""
        if self.is_running():
            return

        self.target = (host, port)
        self.last_error = None
        self.set_effect(effect)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Para a captura e aguarda a thread encerrar."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None

    def _run(self) -> None:
        """Loop de captura (executa na thread)."""
        if not PYAUDIO_AVAILABLE:
            self.last_error = "PyAudio não instalado"
            return

        audio = pyaudio.PyAudio()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        stream = None

        try:
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )

            while not self._stop.is_set():
                raw = stream.read(CHUNK, exception_on_overflow=False)
                sock.sendto(aplicar_efeito(raw, self._current_effect()), self.target)

        except Exception as e:  # noqa: BLE001 - reporta na UI em vez de morrer calado
            self.last_error = str(e)
            print(f"Erro na captura do microfone: {e}")
        finally:
            # stream pode ser None se p.open() falhou — o código antigo
            # levantava NameError aqui e escondia o erro real.
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            audio.terminate()
            sock.close()


@st.cache_resource
def get_mic_controller() -> MicController:
    """Singleton do controlador de microfone (sobrevive aos reruns)."""
    return MicController()


mic = get_mic_controller()


# ============================================================================
# CLIENTE DA API
# ============================================================================


def api_headers(agente: str) -> dict:
    """Header de autenticação da API para o agente selecionado."""
    chave = AGENTES[agente]["api_key"]
    return {"X-API-Key": chave} if chave else {}


def api_get(agente: str, rota: str, timeout: float = 1.5):
    """GET na API do agente. Retorna None em caso de falha."""
    try:
        resposta = requests.get(
            f"{AGENTES[agente]['api_url']}{rota}",
            headers=api_headers(agente),
            timeout=timeout,
        )
        if resposta.status_code == 401:
            st.session_state.api_error = "API_KEY inválida ou ausente"
            return None
        resposta.raise_for_status()
        return resposta.json()
    except requests.RequestException:
        return None


def api_post(agente: str, rota: str, payload: Optional[dict] = None, timeout: float = 5.0):
    """POST na API do agente. Retorna None em caso de falha."""
    try:
        resposta = requests.post(
            f"{AGENTES[agente]['api_url']}{rota}",
            json=payload or {},
            headers=api_headers(agente),
            timeout=timeout,
        )
        if resposta.status_code == 401:
            st.session_state.api_error = "API_KEY inválida ou ausente"
            return None
        resposta.raise_for_status()
        return resposta.json()
    except requests.RequestException as e:
        st.session_state.api_error = str(e)
        return None


# ============================================================================
# ESTADO DA SESSÃO
# ============================================================================

st.session_state.setdefault("current_effect", "Normal")
st.session_state.setdefault("volume_mic", 0.7)
st.session_state.setdefault("volume_fx", 1.0)
st.session_state.setdefault("agent", "Alpha")
st.session_state.setdefault("api_error", None)

# ============================================================================
# HEADER
# ============================================================================

st.markdown(
    """
<div class="main-header">
    <h1>🎛️ Clutch Control Center</h1>
    <p>Interface Premium de Controle de Áudio v3.0</p>
</div>
""",
    unsafe_allow_html=True,
)

# ============================================================================
# SIDEBAR
# ============================================================================

with st.sidebar:
    st.markdown("### 👤 Agente")
    # O widget escreve direto em st.session_state["agent"]: antes a URL da API
    # era calculada antes da seleção, ficando sempre um rerun atrasada.
    st.radio("Selecione o agente:", list(AGENTES), key="agent", horizontal=True)

agente = st.session_state.agent
config_agente = AGENTES[agente]
API_URL = config_agente["api_url"]
UDP_PORT = config_agente["udp_port"]

status = api_get(agente, "/status")
bot_online = status is not None
canal_atual = status.get("channel", "---") if status else "---"
sons_disponiveis = status.get("sounds", []) if status else []
membros = status.get("members", []) if status else []
musica = status.get("music", {}) if status else {}

with st.sidebar:
    status_class = "status-online" if bot_online else "status-offline"
    st.markdown(
        f'<div class="glass-card"><div class="status-badge {status_class}">● '
        f'{"ONLINE" if bot_online else "OFFLINE"}</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(f"**Canal:** {canal_atual}")

    if not config_agente["api_key"]:
        st.caption("⚠️ Sem API_KEY definida — só funciona se o bot estiver em loopback.")

    if st.session_state.api_error:
        st.error(st.session_state.api_error)
        st.session_state.api_error = None

    st.markdown("---")
    st.markdown("### 📡 Conexão")
    channel_id = st.text_input("ID do Canal de Voz", key="channel_id_input")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔗 Conectar", use_container_width=True):
            if not channel_id.strip().isdigit():
                st.error("Informe um ID numérico de canal.")
            else:
                resultado = api_post(agente, "/connect", {"channel_id": channel_id.strip()})
                if resultado:
                    st.success(resultado.get("message", "Conectando..."))
                    st.rerun()

    with col2:
        if st.button("❌ Desconectar", use_container_width=True):
            if api_post(agente, "/disconnect"):
                mic.stop()
                st.success("Desconectado")
                st.rerun()

    st.markdown("---")
    st.markdown("### 🎚️ Volumes")

    volume_mic = st.slider("🎤 Microfone", 0.0, 1.0, st.session_state.volume_mic, 0.05)
    volume_fx = st.slider("🔊 Efeitos", 0.0, 1.0, st.session_state.volume_fx, 0.05)

    # Os sliders agora chegam ao bot: antes o valor só existia no navegador.
    if (volume_mic, volume_fx) != (
        st.session_state.volume_mic,
        st.session_state.volume_fx,
    ):
        st.session_state.volume_mic = volume_mic
        st.session_state.volume_fx = volume_fx
        if api_post(agente, "/volume", {"mic": volume_mic, "fx": volume_fx}):
            st.toast("Volume atualizado no bot")

    st.markdown("---")
    if st.button("🔄 Atualizar status", use_container_width=True):
        st.rerun()
    auto_refresh = st.checkbox("Auto-atualizar (5s)", value=False)

# ============================================================================
# ÁREA PRINCIPAL
# ============================================================================

tab_effects, tab_soundboard, tab_musica, tab_status = st.tabs(
    ["🎭 Efeitos de Voz", "🔊 Soundboard", "🎵 Música", "📊 Status"]
)

with tab_effects:
    col_mic1, col_mic2 = st.columns([1, 2])

    with col_mic1:
        st.markdown("### 🎙️ Transmissão")

        if mic.is_running():
            st.markdown(
                '<div class="status-badge status-transmitting">🔴 TRANSMITINDO</div>',
                unsafe_allow_html=True,
            )
            if st.button("⏹️ Parar", use_container_width=True, type="primary"):
                mic.stop()
                st.rerun()
        else:
            st.markdown(
                '<div class="status-badge status-online">🟢 PRONTO</div>',
                unsafe_allow_html=True,
            )
            if PYAUDIO_AVAILABLE:
                if st.button("▶️ Ativar Microfone", use_container_width=True, type="primary"):
                    mic.start(UDP_IP, UDP_PORT, st.session_state.current_effect)
                    time.sleep(0.3)  # dá tempo da thread reportar erro de device
                    st.rerun()
            else:
                st.warning("⚠️ PyAudio não instalado (pip install -r requirements-dashboard.txt)")

        if mic.last_error:
            st.error(f"Microfone: {mic.last_error}")

    with col_mic2:
        st.markdown("### 👥 Na Call")
        if membros:
            for membro in membros:
                marcador = "🗣️" if membro.get("speaking") else "🔇" if membro.get("muted") else "😐"
                st.markdown(f"{marcador} **{membro.get('name', '?')}**")
        else:
            st.caption("Ninguém na call (ou bot desconectado).")

    st.markdown("### 🎭 Selecione o Efeito de Voz")

    cols = st.columns(4)
    for idx, chave in enumerate(VOICE_EFFECTS):
        efeito = VOICE_EFFECTS[chave]
        ativo = "✅ " if st.session_state.current_effect == chave else ""
        with cols[idx % 4]:
            if st.button(
                f"{ativo}{efeito['icon']} {efeito['name']}",
                key=f"effect_{chave}",
                use_container_width=True,
                help=efeito.get("description", ""),
            ):
                st.session_state.current_effect = chave
                mic.set_effect(chave)  # aplica na thread já em execução
                st.rerun()

    if not PEDALBOARD_AVAILABLE:
        st.info("ℹ️ Pedalboard não instalado — os efeitos ficam desativados.")

with tab_soundboard:
    st.markdown("### 🎵 Soundboard")

    if not bot_online:
        st.warning("Bot offline — não é possível listar os sons.")
    elif not sons_disponiveis:
        st.info(
            "Nenhum som encontrado. Coloque arquivos .mp3 em `assets/sfx/` "
            "(ou no diretório definido em `SOUNDS_DIR`)."
        )
    else:
        sound_cols = st.columns(3)
        for idx, som in enumerate(sons_disponiveis):
            with sound_cols[idx % 3]:
                if st.button(f"🔊 {som}", key=f"som_{som}", use_container_width=True):
                    resultado = api_post(agente, "/play", {"filename": som})
                    if resultado:
                        st.toast(resultado.get("message", "Tocando"))

with tab_musica:
    st.markdown("### 🎵 Player de Música")

    if not bot_online:
        st.warning("Bot offline.")
    elif not musica.get("current"):
        st.info("Nada tocando. Use `/play` no Discord para começar.")
    else:
        atual = musica["current"]

        col_capa, col_info = st.columns([1, 3])
        with col_capa:
            if atual.get("thumbnail"):
                st.image(atual["thumbnail"], use_container_width=True)

        with col_info:
            titulo = atual["title"]
            if atual.get("url"):
                st.markdown(f"#### [{titulo}]({atual['url']})")
            else:
                st.markdown(f"#### {titulo}")

            posicao = musica.get("position", 0)
            duracao = atual.get("duration")

            if duracao:
                st.progress(min(posicao / duracao, 1.0))
                st.caption(
                    f"{formatar_tempo(posicao)} / {formatar_tempo(duracao)} • "
                    f"Volume {musica.get('volume', 0)}% • "
                    f"Repetição: {ROTULOS_LOOP.get(musica.get('loop'), '➡️')}"
                )
            else:
                st.caption("🔴 AO VIVO")

        col_skip, col_stop = st.columns(2)
        with col_skip:
            if st.button("⏭️ Pular", use_container_width=True):
                resultado = api_post(agente, "/music/skip")
                if resultado:
                    st.toast(resultado.get("message", "Pulando"))
                    st.rerun()
        with col_stop:
            if st.button("⏹️ Parar e sair", use_container_width=True):
                resultado = api_post(agente, "/music/stop")
                if resultado:
                    st.toast(resultado.get("message", "Encerrado"))
                    st.rerun()

    fila = musica.get("queue", [])
    total_fila = musica.get("queue_size", 0)

    st.markdown(f"#### 📜 Na fila ({total_fila})")
    if not fila:
        st.caption("_Fila vazia._")
    else:
        for indice, item in enumerate(fila, start=1):
            st.markdown(
                f"`{indice}.` **{item['title']}** "
                f"`{formatar_tempo(item.get('duration'))}`"
            )
        if total_fila > len(fila):
            st.caption(f"… e mais {total_fila - len(fila)} faixas. Veja tudo com `/fila`.")

with tab_status:
    st.markdown("### 📊 Status do Sistema")

    metric_cols = st.columns(4)
    metricas = [
        ("Bot Status", "ONLINE" if bot_online else "OFFLINE"),
        ("Efeito Atual", VOICE_EFFECTS[st.session_state.current_effect]["name"]),
        ("Microfone", "ON" if mic.is_running() else "OFF"),
        ("Na fila", str(musica.get("queue_size", 0))),
    ]

    for coluna, (rotulo, valor) in zip(metric_cols, metricas):
        with coluna:
            st.markdown(
                f'<div class="metric-card"><div class="metric-value">{valor}</div>'
                f'<div class="metric-label">{rotulo}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")
    st.markdown("### 🔧 Informações Técnicas")

    tech_col1, tech_col2 = st.columns(2)
    with tech_col1:
        st.markdown(
            f"""
        **API Endpoint:** `{API_URL}`
        **API Key:** {'✅ definida' if config_agente['api_key'] else '❌ ausente'}
        **UDP Port:** `{UDP_PORT}`
        **Sample Rate:** `{SAMPLE_RATE} Hz`
        **Channels:** `{CHANNELS} (Stereo)`
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

    if status:
        with st.expander("Resposta bruta de /status"):
            st.json(status)

# Auto-refresh opcional. O script antigo terminava com sleep(2)+rerun
# incondicional, criando um loop infinito de recargas.
if auto_refresh:
    time.sleep(5)
    st.rerun()

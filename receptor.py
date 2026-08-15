"""
RECEPTOR DE ÁUDIO
=================

Recebe o áudio capturado pelo bot via UDP e toca nos alto-falantes locais.

Correções:
- O bloco ``finally`` usava ``stream`` mesmo quando ``p.open()`` falhava,
  levantando ``NameError`` e escondendo o erro real (ex: dispositivo ausente).
- A fila era ilimitada: se o player travasse, o processo consumia memória sem
  parar. Agora ela tem tamanho máximo e descarta o pacote mais antigo.
- Ctrl+C agora encerra as duas threads de forma limpa.

Uso:
    python receptor.py
"""

import os
import queue
import socket
import threading

import pyaudio

# --- CONFIGURAÇÕES ---
UDP_IP = os.getenv("UDP_BIND_IP", "0.0.0.0")
UDP_PORT = int(os.getenv("UDP_PORT_ENVIO", "6000"))

# Buffer inicial antes de começar a tocar (~4s em frames de 20ms)
TAMANHO_DO_BUFFER = int(os.getenv("RECEPTOR_BUFFER_SIZE", "200"))
# Teto da fila: evita crescer sem limite se o player parar
MAX_FILA = TAMANHO_DO_BUFFER * 10

# CONFIGURAÇÃO DE ÁUDIO (alinhada 1:1 com o frame do Discord)
FORMAT = pyaudio.paInt16
CHANNELS = int(os.getenv("AUDIO_CHANNELS", "2"))
RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "48000"))
CHUNK = int(os.getenv("AUDIO_CHUNK_SIZE", "960"))  # 20ms exatos

audio_queue: "queue.Queue[bytes]" = queue.Queue(maxsize=MAX_FILA)
parar = threading.Event()


def tocar_audio() -> None:
    """Consome a fila e escreve nos alto-falantes."""
    p = pyaudio.PyAudio()
    stream = None

    try:
        # frames_per_buffer igual ao pacote de rede evita engasgos
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            output=True,
            frames_per_buffer=CHUNK,
        )
        print("🔈 Player sincronizado. Aguardando dados...")

        tocando = False

        while not parar.is_set():
            # Carregamento inicial do buffer
            if not tocando:
                if audio_queue.qsize() >= TAMANHO_DO_BUFFER:
                    print("\n🟢 PLAY! Fluxo estabilizado.")
                    tocando = True
                else:
                    parar.wait(0.01)
                    continue

            try:
                data = audio_queue.get(timeout=2.0)
                stream.write(data)
                audio_queue.task_done()
            except queue.Empty:
                print("\n⚠️ Buffer seco. Recarregando...")
                tocando = False

    except Exception as e:
        print(f"❌ Erro no player: {e}")
    finally:
        # stream pode ser None se p.open() falhou
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        p.terminate()


def iniciar_escuta() -> None:
    """Escuta a porta UDP e alimenta a fila do player."""
    print(f"🎧 RECEPTOR (chunk {CHUNK}) escutando em {UDP_IP}:{UDP_PORT}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
    sock.settimeout(1.0)  # permite checar o evento de parada

    thread_player = threading.Thread(target=tocar_audio, daemon=True)
    thread_player.start()

    print("\n🕵️  Capturando... (Ctrl+C para sair)")

    try:
        while not parar.is_set():
            try:
                data, _ = sock.recvfrom(65536)
            except socket.timeout:
                continue

            try:
                audio_queue.put_nowait(data)
            except queue.Full:
                # Descarta o mais antigo para manter a latência sob controle
                try:
                    audio_queue.get_nowait()
                    audio_queue.put_nowait(data)
                except queue.Empty:
                    pass

            quantidade = audio_queue.qsize()
            if quantidade < TAMANHO_DO_BUFFER and quantidade % 20 == 0:
                print(
                    f"Sincronizando... {quantidade}/{TAMANHO_DO_BUFFER}   ",
                    end="\r",
                )
    except KeyboardInterrupt:
        print("\n🛑 Encerrando receptor...")
    finally:
        parar.set()
        thread_player.join(timeout=3)
        sock.close()


if __name__ == "__main__":
    iniciar_escuta()

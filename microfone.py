"""
MICROFONE (TRANSMISSOR UDP)
===========================

Captura o microfone local e envia via UDP para o bot injetar no canal de voz.

Correções:
- O bloco ``finally`` usava ``stream`` mesmo quando ``p.open()`` falhava,
  levantando ``NameError`` e escondendo o erro real.
- ``KeyboardInterrupt`` não era capturado dentro do laço interno, então o
  Ctrl+C podia ser engolido pelo ``except OSError``.
- Configuração agora vem do .env, em vez de constantes fixas.

Uso:
    python microfone.py
"""

import os
import socket

import pyaudio

# Configurações de rede
UDP_IP = os.getenv("UDP_TARGET_IP", "127.0.0.1")
UDP_PORT = int(os.getenv("UDP_PORT_RECEBIMENTO", "6001"))

# Configuração de áudio (idêntica ao Discord)
FORMAT = pyaudio.paInt16
CHANNELS = int(os.getenv("AUDIO_CHANNELS", "2"))
RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "48000"))
CHUNK = int(os.getenv("AUDIO_CHUNK_SIZE", "960"))  # 20ms exatos


def iniciar_transmissao() -> None:
    """Lê o microfone e transmite os frames PCM via UDP."""
    print(f"🎙️ MICROFONE ATIVO -> enviando para {UDP_IP}:{UDP_PORT}")
    print("Fale para transmitir (Ctrl+C para parar)")

    p = pyaudio.PyAudio()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    stream = None

    try:
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,  # Modo entrada
            frames_per_buffer=CHUNK,
        )

        while True:
            try:
                # exception_on_overflow=False evita derrubar a captura quando
                # o buffer do sistema estoura
                data = stream.read(CHUNK, exception_on_overflow=False)
                sock.sendto(data, (UDP_IP, UDP_PORT))
            except OSError as e:
                print(f"⚠️ Falha de leitura/envio: {e}")

    except KeyboardInterrupt:
        print("\n📻 Câmbio, desligo.")
    except Exception as e:
        print(f"❌ Erro: {e}")
    finally:
        # stream pode ser None se p.open() falhou
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        p.terminate()
        sock.close()


if __name__ == "__main__":
    iniciar_transmissao()

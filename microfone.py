import socket
import pyaudio

# Configurações
UDP_IP = "127.0.0.1" # Manda para o Docker local
UDP_PORT = 6001      # Porta nova que abrimos

# Configuração de Áudio (Idêntica ao Discord)
FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 48000
CHUNK = 960 # 20ms exatos

def iniciar_transmissao():
    print(f"🎙️ MICROFONE ATIVO -> Enviando para {UDP_IP}:{UDP_PORT}")
    print("Fale para transmitir (Ctrl+C para parar)")

    p = pyaudio.PyAudio()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        stream = p.open(format=FORMAT, 
                        channels=CHANNELS, 
                        rate=RATE, 
                        input=True, # Modo Entrada
                        frames_per_buffer=CHUNK)

        while True:
            try:
                # 1. Lê do microfone
                data = stream.read(CHUNK)
                # 2. Joga na rede
                sock.sendto(data, (UDP_IP, UDP_PORT))
            except OSError:
                # Ignora buffer overflow do mic
                pass
            
    except KeyboardInterrupt:
        print("\nCâmbio desligo.")
    except Exception as e:
        print(f"Erro: {e}")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
        sock.close()

if __name__ == "__main__":
    iniciar_transmissao()
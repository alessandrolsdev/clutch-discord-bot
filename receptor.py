import socket
import pyaudio
import queue
import threading
import time

# --- CONFIGURAÇÕES ---
UDP_IP = "0.0.0.0"
UDP_PORT = 6000

# Mantemos o buffer grande para estabilidade (aprox 4s)
TAMANHO_DO_BUFFER = 200 

# CONFIGURAÇÃO DE ÁUDIO (ALINHAMENTO 1:1)
FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 48000
# AQUI ESTAVA O PROBLEMA: Mudamos de (960*2) para 960 exatos.
# Isso casa perfeitamente com o pacote de 20ms do Discord.
CHUNK = 960 

audio_queue = queue.Queue()

def tocar_audio():
    p = pyaudio.PyAudio()
    try:
        # frames_per_buffer igual ao pacote de rede evita engasgos
        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)
        print("🔈 Player Sincronizado. Aguardando dados...")
        
        playing = False

        while True:
            # Lógica de Carregamento Inicial
            if not playing:
                if audio_queue.qsize() >= TAMANHO_DO_BUFFER:
                    print("\n🟢 PLAY! Fluxo estabilizado.")
                    playing = True
                else:
                    time.sleep(0.01)
                    continue

            # Lógica de Reprodução
            try:
                # Pega o pacote exato
                data = audio_queue.get(timeout=2.0)
                stream.write(data) 
                audio_queue.task_done()
            except queue.Empty:
                print("\n⚠️ Buffer seco. Recarregando...")
                playing = False

    except Exception as e:
        print(f"Erro no Player: {e}")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

def iniciar_escuta():
    print(f"🎧 RECEPTOR REFINADO (CHUNK 960) NA PORTA {UDP_PORT}")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    
    # Buffer de rede do Windows no máximo
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)

    thread_player = threading.Thread(target=tocar_audio, daemon=True)
    thread_player.start()

    print(f"\n🕵️‍♂️ CAPTURANDO...")

    while True:
        try:
            # Recebe pacote (64KB max)
            data, addr = sock.recvfrom(65536)
            
            # Coloca na fila
            audio_queue.put(data)
            
            # Visualização do Buffer
            qnt = audio_queue.qsize()
            if qnt < TAMANHO_DO_BUFFER and qnt % 20 == 0:
                print(f"Sincronizando... {qnt}/{TAMANHO_DO_BUFFER}   ", end="\r")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Erro rede: {e}")

if __name__ == "__main__":
    iniciar_escuta()
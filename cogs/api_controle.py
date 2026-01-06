import discord
from discord.ext import commands, voice_recv
from aiohttp import web
import socket
import asyncio
import os
import audioop
import time

# --- CONFIGURAÇÕES DE REDE ---
# IMPORTANTE: Coloque aqui o IP do seu Windows (veja no ipconfig)
UDP_IP_ENVIO = "192.168.10.6" 
UDP_PORT_ENVIO = 6000         # Porta do Receptor (Ouvido)
UDP_PORT_RECEBIMENTO = 6001   # Porta do Microfone (Fala)

class MixerSource(discord.AudioSource):
    """
    Mesa de Som Virtual: Mistura Microfone + Soundboard em tempo real
    """
    def __init__(self):
        # Entrada do Rádio (Walkie-Talkie)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", UDP_PORT_RECEBIMENTO))
        self.sock.setblocking(False)
        
        # Entrada de Efeitos
        self.fx_source = None
        self.current_fx_name = None # Para mostrar no dashboard
        
        # Volumes (1.0 = 100%)
        self.vol_mic = 1.0
        self.vol_fx = 0.5 

    def tocar_efeito(self, caminho, nome_simples):
        """Carrega um som para tocar por cima da voz"""
        try: 
            self.fx_source = discord.FFmpegPCMAudio(caminho)
            self.current_fx_name = nome_simples
            print(f"🎛️ Mixer: Injetando {nome_simples}")
        except Exception as e: 
            print(f"Erro FX: {e}")

    def read(self):
        # 1. Lê Microfone (UDP)
        try: 
            radio_data, _ = self.sock.recvfrom(3840)
        except BlockingIOError: 
            radio_data = b'\x00' * 3840
        
        # Aplica Volume no Mic
        if self.vol_mic != 1.0:
            try: radio_data = audioop.mul(radio_data, 2, self.vol_mic)
            except: pass 

        # 2. Lê Efeitos (MP3)
        fx_data = b'\x00' * 3840
        if self.fx_source:
            try:
                temp = self.fx_source.read()
                if temp:
                    # Preenche com silêncio se o buffer for menor que o esperado
                    if len(temp) < 3840: 
                        temp += b'\x00' * (3840 - len(temp))
                    fx_data = temp
                else:
                    # Som acabou
                    self.fx_source.cleanup()
                    self.fx_source = None
                    self.current_fx_name = None
            except: 
                self.fx_source = None
                self.current_fx_name = None
        
        # Aplica Volume no FX
        if self.vol_fx != 1.0:
            try: fx_data = audioop.mul(fx_data, 2, self.vol_fx)
            except: pass

        # 3. Mistura Final (Soma as ondas)
        return audioop.add(radio_data, fx_data, 2)

    def cleanup(self):
        self.sock.close()
        if self.fx_source: 
            self.fx_source.cleanup()

class APIControle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.transmitting = False
        self.socket_envio = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.mixer = None
        self.speaking_cache = {} # Rastreia quem falou por último

    # --- LOOP DE ÁUDIO (Bot -> Windows) ---
    def callback_audio(self, user, data): 
        if not self.transmitting: return
        
        # Atualiza radar de quem está falando
        if user:
            self.speaking_cache[user.id] = time.time()

        # Envia áudio pro Windows
        if data:
            try: self.socket_envio.sendto(data.pcm, (UDP_IP_ENVIO, UDP_PORT_ENVIO))
            except: pass

    # --- ENDPOINTS DA API (O Cérebro) ---
    async def handle_status(self, request):
        status_bot = "Online" if self.bot.is_ready() else "Offline"
        channel_name = "---"
        members_data = []
        volumes = {'mic': 1.0, 'fx': 0.5}
        
        # Status V8: Feedback Visual
        player_state = "IDLE" 
        current_track = "---"

        if self.bot.voice_clients:
            vc = self.bot.voice_clients[0]
            channel_name = vc.channel.name
            
            if self.mixer:
                volumes['mic'] = self.mixer.vol_mic
                volumes['fx'] = self.mixer.vol_fx
                
                if self.mixer.current_fx_name:
                    player_state = "PLAYING_FX"
                    current_track = self.mixer.current_fx_name
                elif self.transmitting:
                    player_state = "RADIO_ACTIVE"
                    current_track = "Walkie-Talkie (Standby)"

            # Radar de Membros
            now = time.time()
            for member in vc.channel.members:
                if member.id == self.bot.user.id: continue
                
                last_spoke = self.speaking_cache.get(member.id, 0)
                is_speaking = (now - last_spoke) < 0.5 # Falou nos últimos 0.5s?
                
                members_data.append({
                    'name': member.display_name,
                    'avatar': member.display_avatar.url,
                    'speaking': is_speaking,
                    'muted': member.voice.self_mute or member.voice.mute
                })

        # Lista de Sons
        sons = []
        path = "/app/assets/sounds"
        if os.path.exists(path):
            sons = sorted([f for f in os.listdir(path) if f.endswith('.mp3')])

        return web.json_response({
            'status': status_bot, 
            'channel': channel_name, 
            'player_state': player_state,
            'current_track': current_track,
            'members': members_data,
            'volumes': volumes,
            'sounds': sons
        })

    # --- AÇÕES DO BOT ---
    async def conectar_drone(self, channel_id):
        try:
            channel = self.bot.get_channel(int(channel_id))
            if not channel: return "Canal não encontrado (404)."

            if self.bot.voice_clients: 
                await self.bot.voice_clients[0].disconnect()
                await asyncio.sleep(0.5)

            vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
            await vc.guild.change_voice_state(channel=channel, self_mute=False, self_deaf=False)
            
            self.transmitting = True
            self.mixer = MixerSource() # Inicia o Mixer
            
            vc.listen(voice_recv.BasicSink(self.callback_audio))
            vc.play(self.mixer) # Toca o Mixer eternamente
            
            await self.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=f"Alvo: {channel.name}"))
            return f"Conectado: {channel.name}"
        except Exception as e: return str(e)

    async def tocar_som(self, nome_arquivo):
        if not self.mixer: return "Rádio desligado."
        caminho = f"/app/assets/sounds/{nome_arquivo}"
        if not os.path.exists(caminho): return "Arquivo 404"
        
        nome_simples = nome_arquivo.replace(".mp3", "").upper()
        self.mixer.tocar_efeito(caminho, nome_simples)
        return f"Injetado: {nome_simples}"

    async def executar_comando(self, channel_id, texto):
        channel = self.bot.get_channel(int(channel_id))
        if not channel: return "Chat 404"
        
        if texto.startswith(self.bot.command_prefix):
            msg = await channel.send(f"🤖 **CMD:** {texto}")
            ctx = await self.bot.get_context(msg)
            await self.bot.invoke(ctx)
            return "Comando invocado."
        else:
            await channel.send(texto)
            return "Mensagem enviada."

    # --- ROTAS HTTP ---
    async def handle_connect(self, request):
        data = await request.json()
        return web.json_response({'message': await self.conectar_drone(data.get('channel_id'))})
    
    async def handle_disconnect(self, request):
        self.transmitting = False
        self.mixer = None
        if self.bot.voice_clients: await self.bot.voice_clients[0].disconnect()
        return web.json_response({'message': "Desconectado"})

    async def handle_play(self, request):
        data = await request.json()
        return web.json_response({'message': await self.tocar_som(data.get('filename'))})
    
    async def handle_command(self, request):
        data = await request.json()
        return web.json_response({'message': await self.executar_comando(data.get('channel_id'), data.get('text'))})

    async def handle_volume(self, request):
        data = await request.json()
        if self.mixer:
            if 'mic' in data: self.mixer.vol_mic = float(data['mic'])
            if 'fx' in data: self.mixer.vol_fx = float(data['fx'])
        return web.json_response({'msg': 'Volume OK'})

    async def start_server(self):
        app = web.Application()
        app.router.add_get('/status', self.handle_status)
        app.router.add_post('/connect', self.handle_connect)
        app.router.add_post('/disconnect', self.handle_disconnect)
        app.router.add_post('/play', self.handle_play)
        app.router.add_post('/command', self.handle_command)
        app.router.add_post('/volume', self.handle_volume)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        await site.start()
        print("🌐 API V8 (TACTICAL SYSTEM) ONLINE")

    async def cog_load(self): self.bot.loop.create_task(self.start_server())

async def setup(bot): await bot.add_cog(APIControle(bot))
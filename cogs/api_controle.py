import discord
from discord.ext import commands, voice_recv
from aiohttp import web
import socket
import asyncio
import select

# Configurações de Rede
UDP_IP_ENVIO = "192.168.10.6" # IP do seu Windows (para onde o bot manda som)
UDP_PORT_ENVIO = 6000         # Porta do seu Receptor

UDP_PORT_RECEBIMENTO = 6001   # Porta onde o bot ESCUTA seu microfone

class RadioSource(discord.AudioSource):
    """Classe que pega áudio da rede e converte pro Discord"""
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", UDP_PORT_RECEBIMENTO))
        self.sock.setblocking(False)

    def read(self):
        try:
            # Tenta ler 3840 bytes (equivalente a 20ms de áudio estéreo 16bit)
            # Se não tiver nada, lança erro e a gente retorna silêncio
            data, _ = self.sock.recvfrom(3840)
            return data
        except BlockingIOError:
            # Retorna silêncio para manter a conexão ativa
            return b'\x00' * 3840
    
    def cleanup(self):
        self.sock.close()

class APIControle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.transmitting = False
        self.socket_envio = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # --- ENVIO (Bot -> Windows) ---
    def callback_audio(self, user, data): 
        if not self.transmitting or not data: return
        try:
            self.socket_envio.sendto(data.pcm, (UDP_IP_ENVIO, UDP_PORT_ENVIO))
        except: pass

    # --- COMANDOS ---
    async def conectar_drone(self, channel_id):
        try:
            channel = self.bot.get_channel(int(channel_id))
            if not channel: return "Canal 404"

            if self.bot.voice_clients:
                await self.bot.voice_clients[0].disconnect()
                await asyncio.sleep(0.5)

            # 1. Conecta
            vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
            
            # 2. Configura modo 'walkie-talkie' (Mute=False para falar, Deaf=False para ouvir)
            await vc.guild.change_voice_state(channel=channel, self_mute=False, self_deaf=False)
            
            self.transmitting = True
            
            # 3. Inicia ESCUTA (Manda pro seu Windows)
            vc.listen(voice_recv.BasicSink(self.callback_audio))
            
            # 4. Inicia FALA (Toca o que vier do seu Windows)
            vc.play(RadioSource())

            await self.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=f"Rádio: {channel.name}"))
            return f"Conectado: RX/TX Ativos em {channel.name}"
        except Exception as e:
            print(f"Erro: {e}")
            return str(e)

    async def desconectar_drone(self):
        self.transmitting = False
        if self.bot.voice_clients:
            await self.bot.voice_clients[0].disconnect()
            return "Desconectado."
        return "Offline."

    # --- API (Mantida igual para o painel funcionar) ---
    async def handle_connect(self, request):
        data = await request.json()
        msg = await self.conectar_drone(data.get('channel_id'))
        return web.json_response({'message': msg})

    async def handle_disconnect(self, request):
        msg = await self.desconectar_drone()
        return web.json_response({'message': msg})

    async def handle_status(self, request):
        status = "Online" if self.bot.is_ready() else "Offline"
        voice = self.bot.voice_clients[0].channel.name if self.bot.voice_clients else "---"
        return web.json_response({'status': status, 'voice_channel': voice})

    async def start_server(self):
        app = web.Application()
        app.router.add_post('/connect', self.handle_connect)
        app.router.add_post('/disconnect', self.handle_disconnect)
        app.router.add_get('/status', self.handle_status)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        await site.start()
        print("🌐 API RADIO ONLINE")

    async def cog_load(self):
        self.bot.loop.create_task(self.start_server())

async def setup(bot):
    await bot.add_cog(APIControle(bot))
"""
COG: API CONTROLE
=================

Módulo que implementa:
1. API HTTP (aiohttp) para controle remoto do bot via Dashboard
2. MixerSource: Mesa de som virtual que mistura áudio do microfone + soundboard
3. Sistema de captura e transmissão de áudio do Discord via UDP

Arquitetura de Áudio:
┌──────────────┐      UDP       ┌─────────────┐
│Dashboard/Mic │ ──────────────> │  Bot (API)  │
└──────────────┘      6001       └─────────────┘
                                        │
                                        │ MixerSource
                                        ▼
                                 ┌─────────────┐
                                 │   Discord   │
                                 │ Voice Channel│
                                 └─────────────┘
                                        │
                         UDP            │
                         6000           ▼
┌──────────────┐ <────────────── ┌─────────────┐
│Receptor.py   │                 │ Bot (Sink)  │
│(Speaker)     │                 └─────────────┘
└──────────────┘
"""

import discord
from discord.ext import commands, voice_recv
from aiohttp import web
import socket
import asyncio
import os
import audioop
import time
from typing import Optional, Dict, List

# --- CONFIGURAÇÕES DE REDE ---
# Carrega configurações do arquivo .env para segurança
# UDP_TARGET_IP: IP do computador receptor (obtenha com 'ipconfig' no Windows)
# UDP_PORT_ENVIO: Porta do receptor (padrão: 6000)
# UDP_PORT_RECEBIMENTO: Porta do microfone (padrão: 6001)
UDP_IP_ENVIO = os.getenv("UDP_TARGET_IP", "127.0.0.1")
UDP_PORT_ENVIO = int(os.getenv("UDP_PORT_ENVIO", "6000"))
UDP_PORT_RECEBIMENTO = int(os.getenv("UDP_PORT_RECEBIMENTO", "6001"))


class MixerSource(discord.AudioSource):
    """
    Mesa de Som Virtual que mistura duas fontes de áudio em tempo real.

    Fontes:
    1. Microfone/Rádio: Recebido via UDP (walkie-talkie virtual)
    2. Soundboard/FX: Arquivos MP3 tocados on-demand

    O áudio processado é enviado para o canal de voz do Discord.

    Attributes:
        sock: Socket UDP para receber áudio do microfone
        fx_source: Fonte de áudio atual do soundboard (opcional)
        current_fx_name: Nome do efeito sendo tocado
        vol_mic: Volume do microfone (0.0 a 1.0)
        vol_fx: Volume dos efeitos (0.0 a 1.0)
    """

    def __init__(self):
        """Inicializa o mixer com valores padrão."""
        # Entrada do Rádio (Walkie-Talkie via UDP)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", UDP_PORT_RECEBIMENTO))
        self.sock.setblocking(False)  # Non-blocking para não travar o bot

        # Entrada de Efeitos Sonoros
        self.fx_source: Optional[discord.FFmpegPCMAudio] = None
        self.current_fx_name: Optional[str] = None

        # Controles de Volume (0.0 = mudo, 1.0 = 100%)
        self.vol_mic: float = 1.0
        self.vol_fx: float = 0.5

    def tocar_efeito(self, caminho: str, nome_simples: str) -> None:
        """
        Carrega um arquivo de áudio para tocar sobre a voz.

        Args:
            caminho: Caminho absoluto para o arquivo MP3
            nome_simples: Nome legível do efeito (ex: "ALARME")
        """
        try:
            self.fx_source = discord.FFmpegPCMAudio(caminho)
            self.current_fx_name = nome_simples
            print(f"🎛️ Mixer: Injetando {nome_simples}")
        except Exception as e:
            print(f"❌ Erro ao carregar efeito: {e}")

    def read(self) -> bytes:
        """
        Lê 20ms de áudio (3840 bytes) mixado.

        Chamado automaticamente pelo Discord a cada frame (50 vezes/segundo).

        Returns:
            bytes: 3840 bytes de áudio PCM estéreo misturado
        """
        # 1. Lê Microfone via UDP (não-bloqueante)
        try:
            radio_data, _ = self.sock.recvfrom(3840)
        except BlockingIOError:
            # Sem dados disponíveis = silêncio
            radio_data = b"\x00" * 3840

        # Aplica Volume no Microfone
        if self.vol_mic != 1.0:
            try:
                radio_data = audioop.mul(
                    radio_data, 2, self.vol_mic
                )  # 2 = tamanho de sample (16-bit)
            except Exception:
                pass

        # 2. Lê Efeitos Sonoros (se houver)
        fx_data = b"\x00" * 3840
        if self.fx_source:
            try:
                temp = self.fx_source.read()
                if temp:
                    # FFmpeg pode retornar menos de 3840 bytes
                    # Preenche com silêncio para manter sincronização
                    if len(temp) < 3840:
                        temp += b"\x00" * (3840 - len(temp))
                    fx_data = temp
                else:
                    # Som acabou - limpa
                    self.fx_source.cleanup()
                    self.fx_source = None
                    self.current_fx_name = None
            except Exception:
                self.fx_source = None
                self.current_fx_name = None

        # Aplica Volume nos Efeitos
        if self.vol_fx != 1.0:
            try:
                fx_data = audioop.mul(fx_data, 2, self.vol_fx)
            except Exception:
                pass

        # 3. Mistura Final (soma as ondas de áudio)
        # audioop.add soma os dois canais sem clipping automático
        return audioop.add(radio_data, fx_data, 2)

    def cleanup(self) -> None:
        """Libera recursos ao desconectar do canal de voz."""
        self.sock.close()
        if self.fx_source:
            self.fx_source.cleanup()


class APIControle(commands.Cog):
    """
    Cog que expõe API HTTP para controle externo do bot.

    Endpoints:
    - GET  /status: Retorna estado atual do bot
    - POST /connect: Conecta em um canal de voz
    - POST /disconnect: Desconecta do canal
    - POST /play: Toca um som do soundboard
    - POST /command: Executa comando do bot no chat
    - POST /volume: Ajusta volumes do mixer

    Usada pelo Dashboard (Streamlit) para interface visual.
    """

    def __init__(self, bot: commands.Bot):
        """
        Inicializa o cog com referência ao bot.

        Args:
            bot: Instância do ClutchBot
        """
        self.bot = bot
        self.transmitting: bool = False  # Flag se está transmitindo áudio
        self.socket_envio = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.mixer: Optional[MixerSource] = None
        self.speaking_cache: Dict[int, float] = (
            {}
        )  # user_id -> timestamp da última fala

    def callback_audio(self, user: Optional[discord.Member], data) -> None:
        """
        Callback chamado para cada pacote de áudio recebido do Discord.

        Envia o áudio capturado via UDP para o receptor (speakers do Windows).

        Args:
            user: Membro que está falando (pode ser None)
            data: Objeto AudioData com o áudio PCM
        """
        if not self.transmitting:
            return

        # Atualiza radar de quem está falando
        if user:
            self.speaking_cache[user.id] = time.time()

        # Envia áudio bruto (PCM) via UDP para o receptor tocar
        if data:
            try:
                self.socket_envio.sendto(data.pcm, (UDP_IP_ENVIO, UDP_PORT_ENVIO))
            except Exception:
                pass  # Ignora erros de rede silenciosamente

    # --- ENDPOINTS DA API (HTTP) ---

    async def handle_status(self, request: web.Request) -> web.Response:
        """
        GET /status - Retorna estado atual do bot.

        Resposta JSON inclui:
        - status: Online/Offline
        - channel: Nome do canal de voz conectado
        - members: Lista de membros com indicador de quem está falando
        - volumes: Níveis de volume atual
        - sounds: Lista de arquivos disponíveis no soundboard
        """
        status_bot = "Online" if self.bot.is_ready() else "Offline"
        channel_name = "---"
        members_data: List[Dict] = []
        volumes = {"mic": 1.0, "fx": 0.5}

        player_state = "IDLE"
        current_track = "---"

        if self.bot.voice_clients:
            vc = self.bot.voice_clients[0]
            channel_name = vc.channel.name

            if self.mixer:
                volumes["mic"] = self.mixer.vol_mic
                volumes["fx"] = self.mixer.vol_fx

                # Indica visualmente o que está tocando
                if self.mixer.current_fx_name:
                    player_state = "PLAYING_FX"
                    current_track = self.mixer.current_fx_name
                elif self.transmitting:
                    player_state = "RADIO_ACTIVE"
                    current_track = "Walkie-Talkie (Standby)"

            # Radar de Membros com indicador de speaking
            now = time.time()
            for member in vc.channel.members:
                if member.id == self.bot.user.id:
                    continue  # Ignora o próprio bot

                last_spoke = self.speaking_cache.get(member.id, 0)
                is_speaking = (now - last_spoke) < 0.5  # Falou nos últimos 0.5s?

                members_data.append(
                    {
                        "name": member.display_name,
                        "avatar": member.display_avatar.url,
                        "speaking": is_speaking,
                        "muted": member.voice.self_mute or member.voice.mute,
                    }
                )

        # Lista de Sons disponíveis no soundboard
        sons: List[str] = []
        path = "/app/assets/sounds"
        if os.path.exists(path):
            sons = sorted([f for f in os.listdir(path) if f.endswith(".mp3")])

        return web.json_response(
            {
                "status": status_bot,
                "channel": channel_name,
                "player_state": player_state,
                "current_track": current_track,
                "members": members_data,
                "volumes": volumes,
                "sounds": sons,
            }
        )

    async def conectar_drone(self, channel_id: str) -> str:
        """
        Conecta o bot em um canal de voz específico.

        Args:
            channel_id: ID numérico do canal Discord

        Returns:
            str: Mensagem de sucesso ou erro
        """
        try:
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                return "Canal não encontrado (404)."

            # Desconecta de qualquer canal anterior
            if self.bot.voice_clients:
                await self.bot.voice_clients[0].disconnect()
                await asyncio.sleep(0.5)

            # Conecta com VoiceRecvClient (permite receber áudio)
            vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
            await vc.guild.change_voice_state(
                channel=channel,
                self_mute=False,  # Bot não está mudo
                self_deaf=False,  # Bot pode ouvir
            )

            self.transmitting = True
            self.mixer = MixerSource()  # Inicia o mixer

            # Registra callback para capturar áudio do Discord
            vc.listen(voice_recv.BasicSink(self.callback_audio))

            # Inicia reprodução do mixer (loop infinito)
            vc.play(self.mixer)

            # Atualiza status do bot
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.listening, name=f"Alvo: {channel.name}"
                )
            )
            return f"Conectado: {channel.name}"
        except Exception as e:
            return f"Erro: {str(e)}"

    async def tocar_som(self, nome_arquivo: str) -> str:
        """
        Toca um som do soundboard sobre o áudio do microfone.

        Args:
            nome_arquivo: Nome do arquivo MP3 (ex: "alarme.mp3")

        Returns:
            str: Mensagem de sucesso ou erro
        """
        if not self.mixer:
            return "Rádio desligado."

        caminho = f"/app/assets/sounds/{nome_arquivo}"
        if not os.path.exists(caminho):
            return "Arquivo 404"

        nome_simples = nome_arquivo.replace(".mp3", "").upper()
        self.mixer.tocar_efeito(caminho, nome_simples)
        return f"Injetado: {nome_simples}"

    async def executar_comando(self, channel_id: str, texto: str) -> str:
        """
        Envia uma mensagem ou executa um comando no chat.

        Args:
            channel_id: ID do canal de texto
            texto: Mensagem ou comando a enviar

        Returns:
            str: Status da operação
        """
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            return "Chat 404"

        if texto.startswith(self.bot.command_prefix):
            # É um comando - invoca através do bot
            msg = await channel.send(f"🤖 **CMD:** {texto}")
            ctx = await self.bot.get_context(msg)
            await self.bot.invoke(ctx)
            return "Comando invocado."
        else:
            # É uma mensagem comum
            await channel.send(texto)
            return "Mensagem enviada."

    # --- ROTAS HTTP (Handlers) ---

    async def handle_connect(self, request: web.Request) -> web.Response:
        """POST /connect - Conecta em um canal de voz."""
        data = await request.json()
        return web.json_response(
            {"message": await self.conectar_drone(data.get("channel_id"))}
        )

    async def handle_disconnect(self, request: web.Request) -> web.Response:
        """POST /disconnect - Desconecta do canal de voz."""
        self.transmitting = False
        self.mixer = None
        if self.bot.voice_clients:
            await self.bot.voice_clients[0].disconnect()
        return web.json_response({"message": "Desconectado"})

    async def handle_play(self, request: web.Request) -> web.Response:
        """POST /play - Toca um som do soundboard."""
        data = await request.json()
        return web.json_response(
            {"message": await self.tocar_som(data.get("filename"))}
        )

    async def handle_command(self, request: web.Request) -> web.Response:
        """POST /command - Executa comando do bot."""
        data = await request.json()
        return web.json_response(
            {
                "message": await self.executar_comando(
                    data.get("channel_id"), data.get("text")
                )
            }
        )

    async def handle_volume(self, request: web.Request) -> web.Response:
        """POST /volume - Ajusta volumes do mixer."""
        data = await request.json()
        if self.mixer:
            if "mic" in data:
                self.mixer.vol_mic = float(data["mic"])
            if "fx" in data:
                self.mixer.vol_fx = float(data["fx"])
        return web.json_response({"msg": "Volume OK"})

    async def start_server(self) -> None:
        """
        Inicia o servidor HTTP na porta 8080.

        Chamado automaticamente ao carregar o cog.
        """
        app = web.Application()
        app.router.add_get("/status", self.handle_status)
        app.router.add_post("/connect", self.handle_connect)
        app.router.add_post("/disconnect", self.handle_disconnect)
        app.router.add_post("/play", self.handle_play)
        app.router.add_post("/command", self.handle_command)
        app.router.add_post("/volume", self.handle_volume)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8080)
        await site.start()
        print("🌐 API V8 (TACTICAL SYSTEM) ONLINE na porta 8080")

    async def cog_load(self) -> None:
        """Hook executado quando o cog é carregado - inicia a API."""
        self.bot.loop.create_task(self.start_server())


async def setup(bot: commands.Bot) -> None:
    """
    Função obrigatória para carregar o cog.

    Args:
        bot: Instância do bot que carregará este cog
    """
    await bot.add_cog(APIControle(bot))

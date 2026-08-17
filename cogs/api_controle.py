"""
COG: API CONTROLE
=================

Módulo que implementa:
1. API HTTP (aiohttp) para controle remoto do bot via Dashboard
2. MixerSource: Mesa de som virtual que mistura áudio do microfone + soundboard
3. Sistema de captura e transmissão de áudio do Discord via UDP

Segurança:
- Todos os endpoints exigem o header ``X-API-Key`` quando ``API_KEY`` está definido.
- Sem ``API_KEY`` o servidor só sobe em loopback (127.0.0.1), porque estes
  endpoints permitem que o bot entre em canais de voz e envie mensagens.

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

import asyncio
import hmac
import ipaddress
import socket
import time
from pathlib import Path
from typing import Dict, List, Optional

import discord
from aiohttp import web
from discord.ext import commands, voice_recv

from config.settings import settings
from utils.audio_mix import mix_frames, normalize_frame, scale_volume
from utils.logger import get_logger
from utils.soundboard import listar_sons, resolver_som

logger = get_logger(__name__)

# --- CONFIGURAÇÕES DE REDE ---
UDP_IP_ENVIO = settings.audio.udp_target_ip
UDP_PORT_ENVIO = settings.audio.udp_port_send
UDP_PORT_RECEBIMENTO = settings.audio.udp_port_receive

# Diretório único de sons, compartilhado com o cog de áudio (/sfx).
SOUNDS_DIR = Path(settings.audio.sounds_dir).resolve()


class MixerSource(discord.AudioSource):
    """
    Mesa de Som Virtual que mistura duas fontes de áudio em tempo real.

    Fontes:
    1. Microfone/Rádio: Recebido via UDP (walkie-talkie virtual)
    2. Soundboard/FX: Arquivos MP3 tocados on-demand

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
        # SO_REUSEADDR evita "Address already in use" ao reconectar rapidamente.
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", UDP_PORT_RECEBIMENTO))
        self.sock.setblocking(False)  # Non-blocking para não travar o bot

        # Entrada de Efeitos Sonoros
        self.fx_source: Optional[discord.FFmpegPCMAudio] = None
        self.current_fx_name: Optional[str] = None

        # Controles de Volume (0.0 = mudo, 1.0 = 100%)
        self.vol_mic: float = settings.audio.mixer_volume_mic
        self.vol_fx: float = settings.audio.mixer_volume_fx
        self._closed = False

    def tocar_efeito(self, caminho: str, nome_simples: str) -> None:
        """
        Carrega um arquivo de áudio para tocar sobre a voz.

        Args:
            caminho: Caminho absoluto para o arquivo de áudio
            nome_simples: Nome legível do efeito (ex: "ALARME")
        """
        try:
            # Libera o efeito anterior antes de trocar (evita vazar processos ffmpeg)
            self._limpar_fx()
            self.fx_source = discord.FFmpegPCMAudio(caminho)
            self.current_fx_name = nome_simples
            logger.info("Mixer: injetando efeito %s", nome_simples)
        except Exception as e:
            logger.error("Erro ao carregar efeito %s: %s", nome_simples, e)

    def _limpar_fx(self) -> None:
        """Encerra o efeito atual, se houver."""
        if self.fx_source:
            try:
                self.fx_source.cleanup()
            except Exception:
                logger.debug("Falha ao limpar fx_source", exc_info=True)
        self.fx_source = None
        self.current_fx_name = None

    def read(self) -> bytes:
        """
        Lê 20ms de áudio (3840 bytes) mixado.

        Chamado automaticamente pelo Discord a cada frame (50 vezes/segundo).

        Returns:
            bytes: 3840 bytes de áudio PCM estéreo misturado
        """
        if self._closed:
            return b""

        # 1. Lê Microfone via UDP (não-bloqueante).
        # Datagramas podem chegar com tamanho diferente do frame do Discord,
        # então normalizamos para exatamente FRAME_BYTES antes de qualquer
        # operação — audioop exige fragmentos do mesmo tamanho.
        try:
            radio_data, _ = self.sock.recvfrom(65536)
        except (BlockingIOError, InterruptedError):
            radio_data = b""  # Sem dados disponíveis = silêncio
        except OSError:
            logger.debug("Erro ao ler socket UDP do mixer", exc_info=True)
            radio_data = b""

        radio_data = scale_volume(normalize_frame(radio_data), self.vol_mic)

        # 2. Lê Efeitos Sonoros (se houver)
        fx_data = b""
        if self.fx_source:
            try:
                temp = self.fx_source.read()
                if temp:
                    fx_data = temp
                else:
                    self._limpar_fx()  # Som acabou
            except Exception:
                logger.debug("Erro ao ler fx_source", exc_info=True)
                self._limpar_fx()

        fx_data = scale_volume(normalize_frame(fx_data), self.vol_fx)

        # 3. Mistura Final (soma as ondas de áudio, com saturação)
        return mix_frames(radio_data, fx_data)

    def cleanup(self) -> None:
        """Libera recursos ao desconectar do canal de voz."""
        if self._closed:
            return
        self._closed = True
        try:
            self.sock.close()
        except Exception:
            logger.debug("Falha ao fechar socket do mixer", exc_info=True)
        self._limpar_fx()


def _is_loopback(host: str) -> bool:
    """Retorna True se o host for um endereço de loopback."""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in {"localhost", ""}


class APIControle(commands.Cog):
    """
    Cog que expõe API HTTP para controle externo do bot.

    Endpoints (todos exigem X-API-Key quando API_KEY está configurado):
    - GET  /status: Retorna estado atual do bot
    - POST /connect: Conecta em um canal de voz
    - POST /disconnect: Desconecta do canal
    - POST /play: Toca um som do soundboard
    - POST /command: Envia mensagem no chat
    - POST /volume: Ajusta volumes do mixer
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
        self.speaking_cache: Dict[int, float] = {}  # user_id -> ts da última fala
        self.runner: Optional[web.AppRunner] = None
        self._server_task: Optional[asyncio.Task] = None

    def callback_audio(self, user: Optional[discord.Member], data) -> None:
        """
        Callback chamado para cada pacote de áudio recebido do Discord.

        Envia o áudio capturado via UDP para o receptor (speakers).

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
            except OSError:
                logger.debug("Falha ao enviar áudio via UDP", exc_info=True)

    # --- AUTENTICAÇÃO ---

    @web.middleware
    async def auth_middleware(self, request: web.Request, handler):
        """Exige X-API-Key em todas as rotas quando uma chave está configurada."""
        expected = settings.api.api_key
        if expected:
            provided = request.headers.get("X-API-Key", "")
            # compare_digest evita vazar informação por timing
            if not hmac.compare_digest(provided, expected):
                logger.warning(
                    "Requisição não autorizada em %s vinda de %s",
                    request.path,
                    request.remote,
                )
                return web.json_response({"error": "unauthorized"}, status=401)
        return await handler(request)

    def _estado_da_musica(self) -> Dict:
        """
        Resume o player de música para o dashboard.

        Lê o cog Musica sem acoplar os dois: se ele não estiver carregado, a
        API só devolve o bloco desligado.
        """
        vazio = {
            "active": False,
            "current": None,
            "queue": [],
            "queue_size": 0,
            "loop": "off",
            "volume": 0,
            "position": 0,
        }

        musica_cog = self.bot.get_cog("Musica")
        if not musica_cog or not self.bot.voice_clients:
            return vazio

        guild = self.bot.voice_clients[0].guild
        player = musica_cog.players.get(guild.id)
        if player is None:
            return vazio

        atual = player.fila.atual

        return {
            "active": player.tocando,
            "current": (
                {
                    "title": atual.title,
                    "duration": atual.duration,
                    "url": atual.webpage_url,
                    "thumbnail": atual.thumbnail,
                }
                if atual
                else None
            ),
            # Só os 10 primeiros: o dashboard não precisa da fila inteira
            "queue": [
                {"title": t.title, "duration": t.duration}
                for t in list(player.fila.itens)[:10]
            ],
            "queue_size": len(player.fila),
            "loop": player.fila.loop.value,
            "volume": int(player.volume * 100),
            "position": player.posicao_atual,
        }

    def _player_ativo(self):
        """Retorna o GuildPlayer do canal conectado, se houver."""
        musica_cog = self.bot.get_cog("Musica")
        if not musica_cog or not self.bot.voice_clients:
            return None
        return musica_cog.players.get(self.bot.voice_clients[0].guild.id)

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
        volumes = {
            "mic": settings.audio.mixer_volume_mic,
            "fx": settings.audio.mixer_volume_fx,
        }

        player_state = "IDLE"
        current_track = "---"

        if self.bot.voice_clients:
            vc = self.bot.voice_clients[0]
            channel_name = getattr(vc.channel, "name", "---")

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
            for member in getattr(vc.channel, "members", []):
                if self.bot.user and member.id == self.bot.user.id:
                    continue  # Ignora o próprio bot

                last_spoke = self.speaking_cache.get(member.id, 0)
                is_speaking = (now - last_spoke) < 0.5  # Falou nos últimos 0.5s?

                # member.voice é None quando o estado ainda não chegou no cache
                voice_state = member.voice
                muted = bool(
                    voice_state and (voice_state.self_mute or voice_state.mute)
                )

                members_data.append(
                    {
                        "name": member.display_name,
                        "avatar": member.display_avatar.url,
                        "speaking": is_speaking,
                        "muted": muted,
                    }
                )

        return web.json_response(
            {
                "status": status_bot,
                "channel": channel_name,
                "player_state": player_state,
                "current_track": current_track,
                "members": members_data,
                "volumes": volumes,
                "sounds": listar_sons(SOUNDS_DIR),
                "music": self._estado_da_musica(),
            }
        )

    async def conectar_drone(self, channel_id) -> str:
        """
        Conecta o bot em um canal de voz específico.

        Args:
            channel_id: ID numérico do canal Discord

        Returns:
            str: Mensagem de sucesso ou erro
        """
        try:
            channel_id = int(channel_id)
        except (TypeError, ValueError):
            return "channel_id inválido."

        try:
            channel = self.bot.get_channel(channel_id)
            if not isinstance(channel, discord.VoiceChannel):
                return "Canal de voz não encontrado (404)."

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
            logger.error("Erro ao conectar no canal %s: %s", channel_id, e)
            return f"Erro: {e}"

    async def tocar_som(self, nome_arquivo: Optional[str]) -> str:
        """
        Toca um som do soundboard sobre o áudio do microfone.

        Args:
            nome_arquivo: Nome do arquivo (ex: "alarme.mp3")

        Returns:
            str: Mensagem de sucesso ou erro
        """
        if not self.mixer:
            return "Rádio desligado."

        caminho = resolver_som(SOUNDS_DIR, nome_arquivo)
        if caminho is None:
            return "Arquivo 404"

        nome_simples = caminho.stem.upper()
        self.mixer.tocar_efeito(str(caminho), nome_simples)
        return f"Injetado: {nome_simples}"

    async def executar_comando(self, channel_id, texto: Optional[str]) -> str:
        """
        Envia uma mensagem no chat.

        Nota de segurança: esta rota NÃO invoca comandos do bot. Invocar um
        comando a partir de uma mensagem do próprio bot faria ``ctx.author``
        ser o bot, contornando qualquer checagem de permissão dos comandos.

        Args:
            channel_id: ID do canal de texto
            texto: Mensagem a enviar

        Returns:
            str: Status da operação
        """
        if not texto or not texto.strip():
            return "Texto vazio."

        try:
            channel = self.bot.get_channel(int(channel_id))
        except (TypeError, ValueError):
            return "channel_id inválido."

        if not isinstance(channel, discord.abc.Messageable):
            return "Chat 404"

        # Trunca no limite do Discord e neutraliza menções em massa
        conteudo = texto[:2000]
        await channel.send(
            conteudo,
            allowed_mentions=discord.AllowedMentions(
                everyone=False, roles=False, users=True
            ),
        )
        return "Mensagem enviada."

    # --- ROTAS HTTP (Handlers) ---

    @staticmethod
    async def _json_body(request: web.Request) -> dict:
        """Lê o corpo JSON da requisição tolerando corpo vazio/inválido."""
        try:
            data = await request.json()
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    async def handle_connect(self, request: web.Request) -> web.Response:
        """POST /connect - Conecta em um canal de voz."""
        data = await self._json_body(request)
        return web.json_response(
            {"message": await self.conectar_drone(data.get("channel_id"))}
        )

    async def handle_disconnect(self, request: web.Request) -> web.Response:
        """POST /disconnect - Desconecta do canal de voz."""
        self.transmitting = False
        if self.bot.voice_clients:
            # disconnect() dispara AudioSource.cleanup(), que fecha o socket UDP.
            await self.bot.voice_clients[0].disconnect()
        elif self.mixer:
            self.mixer.cleanup()
        self.mixer = None
        self.speaking_cache.clear()
        return web.json_response({"message": "Desconectado"})

    async def handle_play(self, request: web.Request) -> web.Response:
        """POST /play - Toca um som do soundboard."""
        data = await self._json_body(request)
        return web.json_response({"message": await self.tocar_som(data.get("filename"))})

    async def handle_command(self, request: web.Request) -> web.Response:
        """POST /command - Envia uma mensagem em um canal de texto."""
        data = await self._json_body(request)
        return web.json_response(
            {
                "message": await self.executar_comando(
                    data.get("channel_id"), data.get("text")
                )
            }
        )

    async def handle_volume(self, request: web.Request) -> web.Response:
        """POST /volume - Ajusta volumes do mixer."""
        data = await self._json_body(request)
        if not self.mixer:
            return web.json_response({"msg": "Rádio desligado."}, status=409)

        try:
            if "mic" in data:
                self.mixer.vol_mic = min(max(float(data["mic"]), 0.0), 2.0)
            if "fx" in data:
                self.mixer.vol_fx = min(max(float(data["fx"]), 0.0), 2.0)
        except (TypeError, ValueError):
            return web.json_response({"error": "volume inválido"}, status=400)

        return web.json_response(
            {"msg": "Volume OK", "mic": self.mixer.vol_mic, "fx": self.mixer.vol_fx}
        )

    async def handle_music_skip(self, request: web.Request) -> web.Response:
        """POST /music/skip - Pula a faixa atual."""
        player = self._player_ativo()
        if player is None or not player.tocando:
            return web.json_response({"message": "Nada tocando."}, status=409)

        atual = player.fila.atual
        # stop() dispara o callback `after`, que avança a fila
        player.voice_client.stop()
        return web.json_response(
            {"message": f"Pulei: {atual.title if atual else 'faixa'}"}
        )

    async def handle_music_stop(self, request: web.Request) -> web.Response:
        """POST /music/stop - Para a música e limpa a fila."""
        player = self._player_ativo()
        if player is None:
            return web.json_response({"message": "Nada tocando."}, status=409)

        await player.desconectar()
        return web.json_response({"message": "Player encerrado."})

    async def start_server(self) -> None:
        """
        Inicia o servidor HTTP.

        Recusa expor a API fora de loopback sem API_KEY: os endpoints permitem
        conectar o bot em canais de voz e enviar mensagens em nome dele.
        """
        host = settings.api.host
        port = settings.api.port

        if not settings.api.api_key and not _is_loopback(host):
            logger.error(
                "API HTTP NÃO iniciada: host %s é público e API_KEY não está definido. "
                "Defina API_KEY no .env ou use API_HOST=127.0.0.1.",
                host,
            )
            return

        if not settings.api.api_key:
            logger.warning(
                "API HTTP sem autenticação (API_KEY vazio) — escutando apenas em %s.",
                host,
            )

        app = web.Application(middlewares=[self.auth_middleware])
        app.router.add_get("/status", self.handle_status)
        app.router.add_post("/connect", self.handle_connect)
        app.router.add_post("/disconnect", self.handle_disconnect)
        app.router.add_post("/play", self.handle_play)
        app.router.add_post("/command", self.handle_command)
        app.router.add_post("/volume", self.handle_volume)
        app.router.add_post("/music/skip", self.handle_music_skip)
        app.router.add_post("/music/stop", self.handle_music_stop)

        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, host, port)
        await site.start()
        logger.info("🌐 API de controle online em http://%s:%s", host, port)

    async def cog_load(self) -> None:
        """Hook executado quando o cog é carregado - inicia a API."""
        # asyncio.create_task usa o loop em execução; self.bot.loop ainda não
        # existe se o cog for carregado antes do login.
        self._server_task = asyncio.create_task(self.start_server())

    async def cog_unload(self) -> None:
        """Libera servidor HTTP e sockets ao descarregar o cog."""
        if self._server_task:
            self._server_task.cancel()
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
        if self.mixer:
            self.mixer.cleanup()
            self.mixer = None
        self.socket_envio.close()


async def setup(bot: commands.Bot) -> None:
    """
    Função obrigatória para carregar o cog.

    Args:
        bot: Instância do bot que carregará este cog
    """
    await bot.add_cog(APIControle(bot))

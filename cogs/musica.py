"""
COG: MÚSICA
===========

Player com fila, inspirado nos bots de música consagrados (Jockie, Rythm).

Novidades desta versão:
- **Fila de reprodução**: ``/play`` enfileira em vez de cortar a faixa atual.
- **Streaming direto**: o áudio vai do YouTube para o FFmpeg sem passar pelo
  disco. Antes cada música era baixada e convertida para MP3 inteira antes de
  começar a tocar — segundos de espera e I/O desnecessário.
- **Playlists**: um link de playlist enfileira todas as faixas.
- **Auto-disconnect**: sai da call quando fica sozinho ou ocioso.
- **Controle de volume** por servidor, via PCMVolumeTransformer.
- **Cargo DJ**: com mais gente na call, só DJ/moderador controla a fila alheia.

Comandos: /play /pular /fila /tocando /loop /embaralhar /remover /mover
          /limparfila /volume /pausar /retomar /stop
"""

import asyncio
import re
import time
from typing import Dict, List, Optional

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands

from utils.guild_config import guild_config
from utils.logger import get_logger
from utils.musica_fila import (
    Fila,
    LoopMode,
    Track,
    barra_progresso,
    formatar_duracao,
)

logger = get_logger(__name__)

URL_RE = re.compile(r"^https?://", re.IGNORECASE)

# Duração máxima de uma faixa (evita enfileirar streams de 10 horas)
MAX_DURACAO_SEGUNDOS = 60 * 60 * 2

# Máximo de faixas trazidas de uma playlist de uma vez
MAX_ITENS_PLAYLIST = 50

# Tempo ocioso antes de sair sozinho da call
SEGUNDOS_ATE_DESCONECTAR = 180

# Reconecta se o stream cair no meio (comum em conexões longas)
FFMPEG_BEFORE_OPTIONS = (
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
    "-nostdin -loglevel warning"
)
FFMPEG_OPTIONS = "-vn"

YDL_OPTS_BASE = {
    # abr<=128 já é mais do que o Opus do Discord entrega: baixar mais é
    # gastar banda para jogar fora na recodificação.
    "format": "bestaudio[abr<=128]/bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "skip_download": True,
    "extract_flat": False,
    "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
}


class ErroDeBusca(Exception):
    """Falha ao resolver a busca do usuário em faixas tocáveis."""


class GuildPlayer:
    """
    Estado de reprodução de um servidor.

    Mantém a fila, o voice client, a mensagem do player e o temporizador de
    inatividade.
    """

    def __init__(self, cog: "Musica", guild: discord.Guild, limite_fila: int):
        self.cog = cog
        self.guild = guild
        self.fila = Fila(limite=limite_fila)
        self.volume: float = 0.5
        self.text_channel: Optional[discord.abc.Messageable] = None
        self.mensagem_player: Optional[discord.Message] = None
        self.iniciado_em: float = 0.0
        self.pausado_em: Optional[float] = None
        self._tarefa_ociosidade: Optional[asyncio.Task] = None
        self._avancando = asyncio.Lock()

    @property
    def voice_client(self) -> Optional[discord.VoiceClient]:
        """Voice client atual do servidor."""
        return self.guild.voice_client

    @property
    def tocando(self) -> bool:
        """True se há áudio tocando ou pausado."""
        vc = self.voice_client
        return bool(vc and (vc.is_playing() or vc.is_paused()))

    @property
    def posicao_atual(self) -> int:
        """Segundos decorridos da faixa atual."""
        if not self.iniciado_em:
            return 0
        fim = self.pausado_em if self.pausado_em else time.monotonic()
        return int(fim - self.iniciado_em)

    # --- REPRODUÇÃO ---

    def _criar_source(self, track: Track) -> discord.AudioSource:
        """Monta a fonte de áudio (stream remoto) com controle de volume."""
        base = discord.FFmpegPCMAudio(
            track.stream_url,
            before_options=FFMPEG_BEFORE_OPTIONS,
            options=FFMPEG_OPTIONS,
        )
        return discord.PCMVolumeTransformer(base, volume=self.volume)

    async def tocar_proxima(self, pular: bool = False) -> None:
        """
        Avança a fila e começa a tocar a próxima faixa.

        Args:
            pular: True quando veio de /pular (ignora loop de faixa)
        """
        # O lock evita que o callback `after` e um /pular simultâneo
        # avancem a fila duas vezes.
        async with self._avancando:
            voice_client = self.voice_client
            if not voice_client or not voice_client.is_connected():
                return

            track = self.fila.pular() if pular else self.fila.proxima()

            if track is None:
                self.iniciado_em = 0.0
                await self._anunciar_fim_da_fila()
                self.agendar_desconexao()
                return

            self.cancelar_desconexao()

            try:
                source = self._criar_source(track)
            except Exception as e:
                logger.error("Falha ao criar source de %s: %s", track.title, e)
                await self._avisar(f"⚠️ Não consegui tocar **{track.title}**, pulando.")
                # Evita recursão infinita se várias faixas falharem em sequência
                asyncio.create_task(self.tocar_proxima())
                return

            def _after(erro: Optional[Exception]) -> None:
                if erro:
                    logger.error("Erro na reprodução: %s", erro)
                # Volta ao event loop: este callback roda numa thread
                asyncio.run_coroutine_threadsafe(
                    self.tocar_proxima(), self.cog.bot.loop
                )

            voice_client.play(source, after=_after)
            self.iniciado_em = time.monotonic()
            self.pausado_em = None

            await self._anunciar_faixa(track)

    async def _anunciar_faixa(self, track: Track) -> None:
        """Publica o embed 'Tocando agora' com os controles."""
        if self.text_channel is None:
            return

        embed = self.cog.embed_tocando(self, track)
        view = MusicPlayerView(self.cog, self.guild.id)

        try:
            # Substitui o player anterior em vez de empilhar mensagens
            if self.mensagem_player:
                try:
                    await self.mensagem_player.delete()
                except discord.HTTPException:
                    pass

            self.mensagem_player = await self.text_channel.send(embed=embed, view=view)
            view.message = self.mensagem_player
        except discord.HTTPException as e:
            logger.warning("Não foi possível anunciar a faixa: %s", e)

    async def _anunciar_fim_da_fila(self) -> None:
        """Avisa que a fila terminou e desativa os controles."""
        if self.mensagem_player:
            try:
                await self.mensagem_player.edit(view=None)
            except discord.HTTPException:
                pass
            self.mensagem_player = None

        await self._avisar("🏁 Fila finalizada. Saio em 3 min se ninguém pedir nada.")

    async def _avisar(self, texto: str) -> None:
        """Envia um aviso simples no canal de texto do player."""
        if self.text_channel is None:
            return
        try:
            await self.text_channel.send(texto)
        except discord.HTTPException:
            logger.debug("Falha ao enviar aviso do player", exc_info=True)

    # --- INATIVIDADE ---

    def agendar_desconexao(self, segundos: int = SEGUNDOS_ATE_DESCONECTAR) -> None:
        """Agenda a saída automática da call após um período ocioso."""
        self.cancelar_desconexao()
        self._tarefa_ociosidade = asyncio.create_task(self._desconectar_depois(segundos))

    def cancelar_desconexao(self) -> None:
        """Cancela a saída automática (voltou a tocar algo)."""
        if self._tarefa_ociosidade and not self._tarefa_ociosidade.done():
            self._tarefa_ociosidade.cancel()
        self._tarefa_ociosidade = None

    async def _desconectar_depois(self, segundos: int) -> None:
        """Espera e desconecta se continuar ocioso."""
        try:
            await asyncio.sleep(segundos)
        except asyncio.CancelledError:
            return

        if self.tocando:
            return

        await self._avisar("👋 Saindo da call por inatividade.")
        await self.desconectar()

    async def desconectar(self) -> None:
        """Encerra a reprodução, limpa a fila e sai do canal."""
        self.cancelar_desconexao()
        self.fila.resetar()
        self.iniciado_em = 0.0

        if self.mensagem_player:
            try:
                await self.mensagem_player.edit(view=None)
            except discord.HTTPException:
                pass
            self.mensagem_player = None

        voice_client = self.voice_client
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()

        self.cog.players.pop(self.guild.id, None)


class MusicPlayerView(discord.ui.View):
    """Controles do player. Some após 15 min de inatividade da mensagem."""

    def __init__(self, cog: "Musica", guild_id: int):
        super().__init__(timeout=900)
        self.cog = cog
        self.guild_id = guild_id
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Exige que o usuário esteja na mesma call e tenha permissão."""
        return await self.cog.pode_controlar(interaction)

    async def on_timeout(self) -> None:
        """Desabilita os botões quando a view expira."""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.primary)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Alterna entre pausa e reprodução."""
        player = self.cog.players.get(self.guild_id)
        voice_client = player.voice_client if player else None

        if not voice_client:
            return await interaction.response.send_message("❌ Nada tocando.", ephemeral=True)

        if voice_client.is_playing():
            voice_client.pause()
            player.pausado_em = time.monotonic()
            await interaction.response.send_message("⏸️ Pausado!", ephemeral=True)
        elif voice_client.is_paused():
            voice_client.resume()
            # Desloca o início para não contar o tempo pausado no progresso
            if player.pausado_em:
                player.iniciado_em += time.monotonic() - player.pausado_em
                player.pausado_em = None
            await interaction.response.send_message("▶️ Retomado!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nada tocando.", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Pula a faixa atual."""
        player = self.cog.players.get(self.guild_id)
        if not player or not player.tocando:
            return await interaction.response.send_message("❌ Nada tocando.", ephemeral=True)

        await interaction.response.send_message("⏭️ Pulando...", ephemeral=True)
        # stop() dispara o callback `after`, que já avança a fila
        player.fila.loop = (
            LoopMode.OFF if player.fila.loop is LoopMode.TRACK else player.fila.loop
        )
        player.voice_client.stop()

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Alterna entre os modos de repetição."""
        player = self.cog.players.get(self.guild_id)
        if not player:
            return await interaction.response.send_message("❌ Nada tocando.", ephemeral=True)

        ordem = [LoopMode.OFF, LoopMode.TRACK, LoopMode.QUEUE]
        player.fila.loop = ordem[(ordem.index(player.fila.loop) + 1) % len(ordem)]
        await interaction.response.send_message(
            f"Repetição: **{player.fila.loop.rotulo}**", ephemeral=True
        )

    @discord.ui.button(emoji="📜", style=discord.ButtonStyle.secondary)
    async def fila(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Mostra a fila atual."""
        player = self.cog.players.get(self.guild_id)
        if not player:
            return await interaction.response.send_message("❌ Fila vazia.", ephemeral=True)

        await interaction.response.send_message(
            embed=self.cog.embed_fila(player, 1), ephemeral=True
        )

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Para tudo e sai da call."""
        player = self.cog.players.get(self.guild_id)
        if not player:
            return await interaction.response.send_message("❌ Nada tocando.", ephemeral=True)

        await interaction.response.send_message("⏹️ Parando e saindo.", ephemeral=True)
        await player.desconectar()


class Musica(commands.Cog):
    """Cog de reprodução de música com fila."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: Dict[int, GuildPlayer] = {}

    async def cog_unload(self) -> None:
        """Desconecta todos os players ao descarregar o cog."""
        for player in list(self.players.values()):
            await player.desconectar()

    # --- HELPERS ---

    async def get_player(
        self, guild: discord.Guild, text_channel: Optional[discord.abc.Messageable] = None
    ) -> GuildPlayer:
        """Retorna (criando se preciso) o player do servidor."""
        player = self.players.get(guild.id)

        if player is None:
            config = await guild_config.obter(guild.id)
            player = GuildPlayer(self, guild, limite_fila=config.music_max_queue)
            self.players[guild.id] = player

        if text_channel is not None:
            player.text_channel = text_channel

        return player

    async def pode_controlar(self, interaction: discord.Interaction) -> bool:
        """
        Verifica se o usuário pode controlar a reprodução.

        Regras (mesma lógica dos bots de música populares):
        - Precisa estar no mesmo canal de voz do bot
        - Sozinho na call com o bot: controle liberado
        - Com mais gente: exige cargo DJ ou permissão de gerenciar canais

        Responde à interação quando bloqueia.
        """
        voice_client = interaction.guild.voice_client if interaction.guild else None
        voz_usuario = interaction.user.voice

        if not voice_client or not voz_usuario or not voz_usuario.channel:
            await interaction.response.send_message(
                "❌ Você precisa estar no canal de voz para controlar o player.",
                ephemeral=True,
            )
            return False

        if voz_usuario.channel.id != voice_client.channel.id:
            await interaction.response.send_message(
                "❌ Você está em outro canal de voz.", ephemeral=True
            )
            return False

        ouvintes = [m for m in voice_client.channel.members if not m.bot]
        if len(ouvintes) <= 1:
            return True

        permissoes = interaction.user.guild_permissions
        if permissoes.manage_channels or permissoes.administrator:
            return True

        config = await guild_config.obter(interaction.guild.id)
        if config.dj_role_id and any(
            r.id == config.dj_role_id for r in interaction.user.roles
        ):
            return True

        await interaction.response.send_message(
            "❌ Tem mais gente na call — só quem tem o cargo DJ pode controlar.",
            ephemeral=True,
        )
        return False

    def _extrair(self, busca: str) -> List[Track]:
        """
        Resolve a busca em faixas tocáveis (bloqueante, roda em thread).

        Não baixa nada: pega a URL de stream que o FFmpeg consome direto.

        Args:
            busca: URL ou termo de pesquisa

        Returns:
            Lista de faixas (mais de uma em caso de playlist)

        Raises:
            ErroDeBusca: Se nada tocável foi encontrado
        """
        busca = busca.strip()
        e_url = bool(URL_RE.match(busca))
        alvo = busca if e_url else f"ytsearch1:{busca}"

        opcoes = dict(YDL_OPTS_BASE)
        # Só expande playlist quando o usuário colou um link de playlist
        opcoes["noplaylist"] = not e_url
        opcoes["playlistend"] = MAX_ITENS_PLAYLIST

        with yt_dlp.YoutubeDL(opcoes) as ydl:
            info = ydl.extract_info(alvo, download=False)

        if not info:
            raise ErroDeBusca("Nada encontrado para essa busca.")

        entradas = info["entries"] if "entries" in info else [info]
        entradas = [e for e in entradas if e]
        if not entradas:
            raise ErroDeBusca("Nada encontrado para essa busca.")

        faixas: List[Track] = []
        for entrada in entradas:
            duracao = entrada.get("duration")
            if duracao and duracao > MAX_DURACAO_SEGUNDOS:
                continue

            url_stream = entrada.get("url")
            if not url_stream:
                continue

            faixas.append(
                Track(
                    title=entrada.get("title", "Desconhecido"),
                    stream_url=url_stream,
                    webpage_url=entrada.get("webpage_url"),
                    duration=duracao,
                    thumbnail=entrada.get("thumbnail"),
                    uploader=entrada.get("uploader"),
                )
            )

        if not faixas:
            raise ErroDeBusca("Nada tocável encontrado (ou muito longo).")

        return faixas

    def embed_tocando(self, player: GuildPlayer, track: Track) -> discord.Embed:
        """Monta o embed 'Tocando agora'."""
        embed = discord.Embed(
            title="💿 Tocando Agora",
            description=(
                f"**[{track.title}]({track.webpage_url})**"
                if track.webpage_url
                else f"**{track.title}**"
            ),
            color=discord.Color.purple(),
        )

        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)

        embed.add_field(
            name="Progresso",
            value=(
                f"{barra_progresso(player.posicao_atual, track.duration)}\n"
                f"`{formatar_duracao(player.posicao_atual)} / {track.duracao_formatada}`"
            ),
            inline=False,
        )
        embed.add_field(name="🔊 Volume", value=f"{int(player.volume * 100)}%", inline=True)
        embed.add_field(name="🔁 Repetição", value=player.fila.loop.rotulo, inline=True)
        embed.add_field(name="📜 Na fila", value=f"{len(player.fila)}", inline=True)

        if track.requester_id:
            embed.set_footer(text=f"Pedido por: {track.requester_id}")

        return embed

    def embed_fila(self, player: GuildPlayer, pagina: int) -> discord.Embed:
        """Monta o embed da fila paginada."""
        pagina = max(1, min(pagina, player.fila.total_paginas))
        faixas = player.fila.pagina(pagina)
        inicio = (pagina - 1) * 10

        embed = discord.Embed(title="📜 Fila de Reprodução", color=discord.Color.blurple())

        if player.fila.atual:
            embed.add_field(
                name="▶️ Tocando agora",
                value=f"**{player.fila.atual.title}** `{player.fila.atual.duracao_formatada}`",
                inline=False,
            )

        if faixas:
            linhas = "\n".join(
                f"`{inicio + i + 1}.` **{t.title}** `{t.duracao_formatada}`"
                for i, t in enumerate(faixas)
            )
            embed.add_field(name="A seguir", value=linhas, inline=False)
        else:
            embed.add_field(name="A seguir", value="_Fila vazia._", inline=False)

        total = player.fila.duracao_total
        embed.set_footer(
            text=(
                f"Página {pagina}/{player.fila.total_paginas} • "
                f"{len(player.fila)} na fila • "
                f"Duração: {formatar_duracao(total) if total else '──:──'} • "
                f"Repetição: {player.fila.loop.rotulo}"
            )
        )
        return embed

    # --- LISTENERS ---

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Sai da call quando o bot fica sozinho."""
        if not member.guild:
            return

        player = self.players.get(member.guild.id)
        if not player:
            return

        voice_client = player.voice_client
        if not voice_client or not voice_client.is_connected():
            return

        # O próprio bot foi desconectado à força
        if member.id == self.bot.user.id and after.channel is None:
            await player.desconectar()
            return

        humanos = [m for m in voice_client.channel.members if not m.bot]

        if not humanos:
            logger.info("Canal vazio em %s: agendando saída", member.guild.id)
            player.agendar_desconexao(60)
        else:
            # Alguém voltou antes do timeout: cancela só se ainda há o que tocar
            if player.tocando:
                player.cancelar_desconexao()

    # --- COMANDOS ---

    @app_commands.command(name="play", description="Toca ou enfileira uma música")
    @app_commands.describe(busca="Nome da música, link do YouTube ou playlist")
    @app_commands.guild_only()
    async def play(self, interaction: discord.Interaction, busca: str):
        """Enfileira uma faixa (ou uma playlist inteira)."""
        busca = busca.strip()
        if not busca:
            return await interaction.response.send_message(
                "❌ Informe o nome ou o link da música.", ephemeral=True
            )

        if not (interaction.user.voice and interaction.user.voice.channel):
            return await interaction.response.send_message(
                "❌ Entre num canal de voz primeiro!", ephemeral=True
            )

        await interaction.response.defer()

        canal = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        try:
            if voice_client is None:
                voice_client = await canal.connect()
            elif voice_client.channel.id != canal.id and not voice_client.is_playing():
                await voice_client.move_to(canal)
        except (discord.ClientException, asyncio.TimeoutError) as e:
            return await interaction.followup.send(f"❌ Não consegui entrar: {e}")

        player = await self.get_player(interaction.guild, interaction.channel)

        try:
            # Resolver a busca é bloqueante: vai para uma thread
            faixas = await asyncio.to_thread(self._extrair, busca)
        except ErroDeBusca as e:
            return await interaction.followup.send(f"❌ {e}")
        except yt_dlp.utils.DownloadError as e:
            logger.warning("Falha ao resolver %r: %s", busca, e)
            return await interaction.followup.send(
                "❌ Não consegui acessar esse áudio (indisponível ou restrito)."
            )
        except Exception as e:
            logger.error("Erro inesperado no /play: %s", e, exc_info=True)
            return await interaction.followup.send(f"❌ Erro: {e}")

        adicionadas = 0
        for faixa in faixas:
            faixa.requester_id = interaction.user.id
            if not player.fila.adicionar(faixa):
                break
            adicionadas += 1

        if adicionadas == 0:
            return await interaction.followup.send(
                f"❌ Fila cheia (limite: {player.fila.limite})."
            )

        descartadas = len(faixas) - adicionadas

        if not player.tocando:
            await interaction.followup.send(
                f"🎶 Tocando **{faixas[0].title}**"
                + (f" (+{adicionadas - 1} da playlist)" if adicionadas > 1 else "")
            )
            await player.tocar_proxima()
        else:
            posicao = len(player.fila)
            if adicionadas == 1:
                await interaction.followup.send(
                    f"➕ **{faixas[0].title}** adicionada na posição **{posicao}**."
                )
            else:
                await interaction.followup.send(
                    f"➕ **{adicionadas}** faixas adicionadas à fila."
                    + (f" ({descartadas} descartadas: fila cheia)" if descartadas else "")
                )

    @app_commands.command(name="pular", description="Pula a música atual")
    @app_commands.guild_only()
    async def pular(self, interaction: discord.Interaction):
        """Pula para a próxima faixa da fila."""
        if not await self.pode_controlar(interaction):
            return

        player = self.players.get(interaction.guild.id)
        if not player or not player.tocando:
            return await interaction.response.send_message(
                "❌ Não estou tocando nada.", ephemeral=True
            )

        atual = player.fila.atual
        await interaction.response.send_message(
            f"⏭️ Pulei **{atual.title if atual else 'a faixa'}**."
        )

        if player.fila.loop is LoopMode.TRACK:
            player.fila.loop = LoopMode.OFF
        player.voice_client.stop()  # dispara `after` -> tocar_proxima()

    @app_commands.command(name="fila", description="Mostra a fila de reprodução")
    @app_commands.describe(pagina="Página da fila")
    @app_commands.guild_only()
    async def fila(self, interaction: discord.Interaction, pagina: int = 1):
        """Exibe a fila paginada."""
        player = self.players.get(interaction.guild.id)
        if not player or (not player.fila.atual and not len(player.fila)):
            return await interaction.response.send_message(
                "❌ A fila está vazia.", ephemeral=True
            )

        await interaction.response.send_message(embed=self.embed_fila(player, pagina))

    @app_commands.command(name="tocando", description="Mostra a música atual")
    @app_commands.guild_only()
    async def tocando(self, interaction: discord.Interaction):
        """Mostra a faixa atual com barra de progresso."""
        player = self.players.get(interaction.guild.id)
        if not player or not player.fila.atual:
            return await interaction.response.send_message(
                "❌ Não estou tocando nada.", ephemeral=True
            )

        await interaction.response.send_message(
            embed=self.embed_tocando(player, player.fila.atual)
        )

    @app_commands.command(name="loop", description="Muda o modo de repetição")
    @app_commands.choices(
        modo=[
            app_commands.Choice(name="➡️ Desligado", value="off"),
            app_commands.Choice(name="🔂 Repetir faixa", value="track"),
            app_commands.Choice(name="🔁 Repetir fila", value="queue"),
        ]
    )
    @app_commands.guild_only()
    async def loop(self, interaction: discord.Interaction, modo: app_commands.Choice[str]):
        """Define o modo de repetição."""
        if not await self.pode_controlar(interaction):
            return

        player = self.players.get(interaction.guild.id)
        if not player:
            return await interaction.response.send_message(
                "❌ Não estou tocando nada.", ephemeral=True
            )

        player.fila.loop = LoopMode(modo.value)
        await interaction.response.send_message(
            f"Repetição: **{player.fila.loop.rotulo}**"
        )

    @app_commands.command(name="embaralhar", description="Embaralha a fila")
    @app_commands.guild_only()
    async def embaralhar(self, interaction: discord.Interaction):
        """Embaralha as faixas aguardando."""
        if not await self.pode_controlar(interaction):
            return

        player = self.players.get(interaction.guild.id)
        if not player or len(player.fila) < 2:
            return await interaction.response.send_message(
                "❌ Preciso de pelo menos 2 faixas na fila.", ephemeral=True
            )

        player.fila.embaralhar()
        await interaction.response.send_message(
            f"🔀 Fila embaralhada ({len(player.fila)} faixas)."
        )

    @app_commands.command(name="remover", description="Remove uma faixa da fila")
    @app_commands.describe(posicao="Posição na fila (veja em /fila)")
    @app_commands.guild_only()
    async def remover(self, interaction: discord.Interaction, posicao: int):
        """Remove uma faixa específica da fila."""
        if not await self.pode_controlar(interaction):
            return

        player = self.players.get(interaction.guild.id)
        if not player:
            return await interaction.response.send_message(
                "❌ A fila está vazia.", ephemeral=True
            )

        removida = player.fila.remover(posicao)
        if removida is None:
            return await interaction.response.send_message(
                f"❌ Posição inválida (a fila tem {len(player.fila)} faixas).",
                ephemeral=True,
            )

        await interaction.response.send_message(f"🗑️ Removi **{removida.title}**.")

    @app_commands.command(name="mover", description="Muda uma faixa de posição")
    @app_commands.describe(origem="Posição atual", destino="Nova posição")
    @app_commands.guild_only()
    async def mover(self, interaction: discord.Interaction, origem: int, destino: int):
        """Reordena a fila."""
        if not await self.pode_controlar(interaction):
            return

        player = self.players.get(interaction.guild.id)
        if not player:
            return await interaction.response.send_message(
                "❌ A fila está vazia.", ephemeral=True
            )

        movida = player.fila.mover(origem, destino)
        if movida is None:
            return await interaction.response.send_message(
                f"❌ Posições inválidas (a fila tem {len(player.fila)} faixas).",
                ephemeral=True,
            )

        await interaction.response.send_message(
            f"↕️ **{movida.title}** foi para a posição **{destino}**."
        )

    @app_commands.command(name="limparfila", description="Esvazia a fila")
    @app_commands.guild_only()
    async def limparfila(self, interaction: discord.Interaction):
        """Remove todas as faixas aguardando (mantém a atual)."""
        if not await self.pode_controlar(interaction):
            return

        player = self.players.get(interaction.guild.id)
        if not player:
            return await interaction.response.send_message(
                "❌ A fila já está vazia.", ephemeral=True
            )

        total = player.fila.limpar()
        await interaction.response.send_message(f"🧹 Removi **{total}** faixas da fila.")

    @app_commands.command(name="volume", description="Ajusta o volume da música")
    @app_commands.describe(nivel="Volume de 0 a 150 (%)")
    @app_commands.guild_only()
    async def volume(self, interaction: discord.Interaction, nivel: app_commands.Range[int, 0, 150]):
        """Ajusta o volume da reprodução."""
        if not await self.pode_controlar(interaction):
            return

        player = self.players.get(interaction.guild.id)
        if not player:
            return await interaction.response.send_message(
                "❌ Não estou tocando nada.", ephemeral=True
            )

        player.volume = nivel / 100

        # Aplica na fonte que já está tocando
        voice_client = player.voice_client
        if voice_client and isinstance(voice_client.source, discord.PCMVolumeTransformer):
            voice_client.source.volume = player.volume

        await interaction.response.send_message(f"🔊 Volume: **{nivel}%**")

    @app_commands.command(name="pausar", description="Pausa a música")
    @app_commands.guild_only()
    async def pausar(self, interaction: discord.Interaction):
        """Pausa a reprodução."""
        if not await self.pode_controlar(interaction):
            return

        player = self.players.get(interaction.guild.id)
        voice_client = player.voice_client if player else None

        if not voice_client or not voice_client.is_playing():
            return await interaction.response.send_message(
                "❌ Nada tocando.", ephemeral=True
            )

        voice_client.pause()
        player.pausado_em = time.monotonic()
        await interaction.response.send_message("⏸️ Pausado.")

    @app_commands.command(name="retomar", description="Retoma a música pausada")
    @app_commands.guild_only()
    async def retomar(self, interaction: discord.Interaction):
        """Retoma a reprodução pausada."""
        if not await self.pode_controlar(interaction):
            return

        player = self.players.get(interaction.guild.id)
        voice_client = player.voice_client if player else None

        if not voice_client or not voice_client.is_paused():
            return await interaction.response.send_message(
                "❌ Não estou pausado.", ephemeral=True
            )

        voice_client.resume()
        if player.pausado_em:
            player.iniciado_em += time.monotonic() - player.pausado_em
            player.pausado_em = None

        await interaction.response.send_message("▶️ Retomado.")

    @app_commands.command(name="stop", description="Para a música e sai da call")
    @app_commands.guild_only()
    async def stop_cmd(self, interaction: discord.Interaction):
        """Para tudo, limpa a fila e desconecta."""
        if not await self.pode_controlar(interaction):
            return

        player = self.players.get(interaction.guild.id)
        if not player:
            return await interaction.response.send_message(
                "😐 Não estou tocando nada.", ephemeral=True
            )

        await interaction.response.send_message("⏹️ Parei e limpei a fila.")
        await player.desconectar()


async def setup(bot: commands.Bot):
    await bot.add_cog(Musica(bot))

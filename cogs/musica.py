"""
COG: MÚSICA
===========

Reprodução de áudio do YouTube com controles interativos.

Correções relevantes:
- Links diretos funcionam: antes tudo era prefixado com ``ytsearch1:``, então
  colar uma URL fazia o yt-dlp *pesquisar pela URL* em vez de abri-la.
- Os arquivos baixados são apagados ao terminar; antes ficavam acumulando em
  ``temp/`` até encher o disco.
- ``nocheckcertificate`` foi removido (desligava a verificação de TLS).
- Os botões consultam o voice client atual do servidor em vez de guardar uma
  referência que fica obsoleta após uma reconexão.
"""

import asyncio
import re
from pathlib import Path
from typing import Optional

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands

from utils.logger import get_logger

logger = get_logger(__name__)

TEMP_DIR = Path("temp")

# Duração máxima aceita (evita baixar streams de 10h e lotar o disco)
MAX_DURACAO_SEGUNDOS = 60 * 15

URL_RE = re.compile(r"^https?://", re.IGNORECASE)


class MusicPlayerView(discord.ui.View):
    """Botões de controle do player."""

    def __init__(self, guild_id: int, titulo: str):
        super().__init__(timeout=900)  # 15 min; depois os botões se desativam
        self.guild_id = guild_id
        self.titulo = titulo
        self.message: Optional[discord.Message] = None

    def _voice_client(
        self, interaction: discord.Interaction
    ) -> Optional[discord.VoiceClient]:
        """Voice client atual do servidor (não uma referência congelada)."""
        return interaction.guild.voice_client if interaction.guild else None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Só quem está na mesma call pode controlar a reprodução."""
        voice_client = self._voice_client(interaction)
        usuario_em_call = interaction.user.voice and interaction.user.voice.channel

        if not voice_client or not usuario_em_call:
            await interaction.response.send_message(
                "❌ Você precisa estar no canal de voz para controlar o player.",
                ephemeral=True,
            )
            return False

        if interaction.user.voice.channel.id != voice_client.channel.id:
            await interaction.response.send_message(
                "❌ Você está em outro canal de voz.", ephemeral=True
            )
            return False

        return True

    async def _desativar(self) -> None:
        """Desabilita os botões na mensagem original."""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                logger.debug("Não foi possível desabilitar os botões", exc_info=True)

    async def on_timeout(self) -> None:
        """Desabilita os controles quando a view expira."""
        await self._desativar()

    @discord.ui.button(
        label="Pausar/Retomar", style=discord.ButtonStyle.primary, emoji="⏯️"
    )
    async def pause_resume(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Alterna entre pausa e reprodução."""
        voice_client = self._voice_client(interaction)

        if voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message("⏸️ Pausado!", ephemeral=True)
        elif voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message("▶️ Retomado!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nada tocando.", ephemeral=True)

    @discord.ui.button(label="Parar", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Para a reprodução e desativa os controles."""
        voice_client = self._voice_client(interaction)

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
            await interaction.response.send_message("⏹️ Música parada.", ephemeral=True)
            await self._desativar()
            self.stop()
        else:
            await interaction.response.send_message("❌ Já estou parado.", ephemeral=True)


class Musica(commands.Cog):
    """Cog de reprodução de música."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        self.ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "outtmpl": str(TEMP_DIR / "musica_%(id)s.%(ext)s"),
            "quiet": True,
            "ignoreerrors": False,
            "logtostderr": False,
            "no_warnings": True,
            "noplaylist": True,  # Um link de playlist não baixa 200 faixas
            "match_filter": yt_dlp.utils.match_filter_func(
                f"duration < {MAX_DURACAO_SEGUNDOS}"
            ),
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web"],
                    "skip": ["hls", "dash"],
                }
            },
        }

    def _download(self, busca: str) -> dict:
        """
        Baixa o áudio (função síncrona, executada em thread separada).

        Args:
            busca: URL ou termo de busca

        Returns:
            dict com arquivo, titulo, thumbnail e duracao
        """
        # Uma URL vai direto para o extrator; texto vira busca no YouTube
        alvo = busca if URL_RE.match(busca.strip()) else f"ytsearch1:{busca}"

        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            info = ydl.extract_info(alvo, download=True)

            if info is None:
                raise ValueError("Nada encontrado (ou vídeo muito longo).")

            if "entries" in info:
                entries = [e for e in info["entries"] if e]
                if not entries:
                    raise ValueError("Nada encontrado para essa busca.")
                info = entries[0]

            # prepare_filename devolve a extensão de origem; o postprocessor
            # converte para .mp3, então trocamos o sufixo pelo caminho real.
            arquivo = Path(ydl.prepare_filename(info)).with_suffix(".mp3")

            return {
                "arquivo": arquivo,
                "titulo": info.get("title", "Desconhecido"),
                "thumbnail": info.get("thumbnail"),
                "duracao": info.get("duration"),
            }

    async def _tocar(
        self, voice_client: discord.VoiceClient, caminho: Path
    ) -> None:
        """
        Toca o arquivo e o apaga quando a reprodução termina.

        Args:
            voice_client: Cliente de voz conectado
            caminho: Arquivo baixado
        """
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()

        def _after(erro: Optional[Exception]) -> None:
            # Roda numa thread do discord.py: só limpeza de arquivo aqui
            if erro:
                logger.error("Erro na reprodução da música: %s", erro)
            try:
                caminho.unlink(missing_ok=True)
            except OSError:
                logger.debug("Não foi possível remover %s", caminho, exc_info=True)

        source = discord.FFmpegPCMAudio(source=str(caminho), executable="ffmpeg")
        voice_client.play(source, after=_after)
        await asyncio.sleep(0)  # cede o controle ao loop

    @app_commands.command(name="play", description="Toca uma música do YouTube")
    @app_commands.describe(busca="Nome da música ou Link")
    @app_commands.guild_only()
    async def play(self, interaction: discord.Interaction, busca: str):
        """Busca, baixa e toca uma música."""
        busca = busca.strip()
        if not busca:
            return await interaction.response.send_message(
                "❌ Informe o nome ou o link da música.", ephemeral=True
            )

        if not (interaction.user.voice and interaction.user.voice.channel):
            return await interaction.response.send_message(
                "❌ Entre num canal de voz primeiro!", ephemeral=True
            )

        # O download demora: avisa o Discord antes de qualquer trabalho pesado
        await interaction.response.defer()

        canal = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        try:
            if voice_client is None:
                voice_client = await canal.connect()
            elif voice_client.channel.id != canal.id:
                await voice_client.move_to(canal)
        except (discord.ClientException, asyncio.TimeoutError) as e:
            return await interaction.followup.send(f"❌ Não consegui entrar: {e}")

        arquivo: Optional[Path] = None
        try:
            # Download é bloqueante: roda em thread para não travar o bot
            data = await asyncio.to_thread(self._download, busca)
            arquivo = data["arquivo"]

            if not arquivo.is_file():
                raise FileNotFoundError(f"Arquivo não encontrado após download: {arquivo}")

            await self._tocar(voice_client, arquivo)

            embed = discord.Embed(
                title="💿 Tocando Agora",
                description=f"**{data['titulo']}**",
                color=discord.Color.purple(),
            )
            if data.get("thumbnail"):
                embed.set_thumbnail(url=data["thumbnail"])
            if data.get("duracao"):
                minutos, segundos = divmod(int(data["duracao"]), 60)
                embed.add_field(name="Duração", value=f"{minutos}:{segundos:02d}")
            embed.set_footer(text=f"Pedido por {interaction.user.display_name}")

            view = MusicPlayerView(interaction.guild.id, data["titulo"])
            view.message = await interaction.followup.send(embed=embed, view=view)

        except yt_dlp.utils.DownloadError as e:
            logger.warning("Falha no download de %r: %s", busca, e)
            if arquivo:
                arquivo.unlink(missing_ok=True)
            await interaction.followup.send(
                "❌ Não consegui baixar esse áudio (indisponível, restrito ou longo demais)."
            )
        except Exception as e:
            logger.error("Erro no /play: %s", e, exc_info=True)
            if arquivo:
                arquivo.unlink(missing_ok=True)
            await interaction.followup.send(f"❌ Erro: {e}")

    @app_commands.command(name="stop", description="Para a música")
    @app_commands.guild_only()
    async def stop_cmd(self, interaction: discord.Interaction):
        """Para a reprodução atual."""
        voice_client = interaction.guild.voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await interaction.response.send_message("⏹️ Parado.")
        else:
            await interaction.response.send_message(
                "😐 Não estou tocando nada.", ephemeral=True
            )

    async def cog_unload(self) -> None:
        """Remove downloads que tenham sobrado."""
        for arquivo in TEMP_DIR.glob("musica_*"):
            arquivo.unlink(missing_ok=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Musica(bot))

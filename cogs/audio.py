"""
COG: ÁUDIO
==========

Gerencia todas as funcionalidades de áudio do bot:
- Text-to-Speech (TTS) em português brasileiro
- Efeitos sonoros (SFX) com autocomplete
- Conexão/desconexão de canais de voz
- Controle de reprodução

Notas de implementação:
- Cada TTS gera um arquivo temporário **único**. Antes todos escreviam em
  ``temp/fala.mp3``, então dois usuários simultâneos sobrescreviam (e apagavam)
  o áudio um do outro.
- A reprodução espera o callback ``after`` do discord.py em vez de fazer
  polling com ``sleep``, e é serializada por servidor com um lock.

Dependências:
- edge-tts: Vozes naturais da Microsoft
- FFmpeg: Codificação de áudio
- PyNaCl: Criptografia de voz do Discord
"""

import asyncio
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import discord
import edge_tts
from discord import app_commands
from discord.ext import commands

from config.settings import settings
from utils.logger import get_logger
from utils.soundboard import EXTENSOES_VALIDAS, resolver_som

logger = get_logger(__name__)

TEMP_DIR = Path("temp")
SOUNDS_DIR = Path(settings.audio.sounds_dir)

# Limite do Edge TTS por requisição (evita payloads absurdos)
MAX_TTS_CHARS = 500


class Audio(commands.Cog):
    """Cog de TTS, soundboard e controle de canal de voz."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voz_padrao = "pt-BR-AntonioNeural"
        # Um lock por servidor: evita duas reproduções disputando o mesmo canal
        self._locks: Dict[int, asyncio.Lock] = {}

    def _lock(self, guild_id: int) -> asyncio.Lock:
        """Retorna (criando se preciso) o lock de reprodução do servidor."""
        if guild_id not in self._locks:
            self._locks[guild_id] = asyncio.Lock()
        return self._locks[guild_id]

    # --- MÉTODOS AUXILIARES ---

    async def gerar_tts(self, texto: str) -> Path:
        """
        Gera arquivo de áudio TTS a partir de texto.

        Utiliza Edge TTS da Microsoft para vozes naturais em PT-BR.

        Args:
            texto: Texto a ser convertido em fala

        Returns:
            Path: Caminho do MP3 gerado (nome único, deve ser apagado após uso)
        """
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        caminho = TEMP_DIR / f"tts_{uuid.uuid4().hex}.mp3"

        communicate = edge_tts.Communicate(texto[:MAX_TTS_CHARS], self.voz_padrao)
        await communicate.save(str(caminho))

        return caminho

    async def reproduzir(
        self,
        voice_client: discord.VoiceClient,
        caminho: Path,
        apagar_depois: bool = False,
    ) -> None:
        """
        Toca um arquivo no canal de voz e aguarda o fim da reprodução.

        Args:
            voice_client: Cliente de voz conectado
            caminho: Arquivo de áudio a tocar
            apagar_depois: Se True, remove o arquivo ao terminar
        """
        loop = asyncio.get_running_loop()

        async with self._lock(voice_client.guild.id):
            if voice_client.is_playing():
                voice_client.stop()

            terminou: asyncio.Future = loop.create_future()

            def _after(erro: Optional[Exception]) -> None:
                # Chamado numa thread do discord.py: volta ao loop com segurança
                if erro:
                    logger.error("Erro durante a reprodução: %s", erro)
                if not terminou.done():
                    loop.call_soon_threadsafe(terminou.set_result, True)

            try:
                source = discord.FFmpegPCMAudio(source=str(caminho), executable="ffmpeg")
                voice_client.play(source, after=_after)
                await terminou
            finally:
                if apagar_depois:
                    caminho.unlink(missing_ok=True)

    async def falar(self, guild: discord.Guild, texto: str) -> None:
        """
        Gera TTS e reproduz no canal de voz do servidor.

        Usado por outros cogs (ex: /chat, /vibe). Não faz nada se o bot não
        estiver conectado.

        Args:
            guild: Servidor onde falar
            texto: Texto a ser falado
        """
        voice_client = guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return

        caminho = await self.gerar_tts(texto)
        await self.reproduzir(voice_client, caminho, apagar_depois=True)

    async def _garantir_conexao(
        self, interaction: discord.Interaction
    ) -> Optional[discord.VoiceClient]:
        """
        Garante que o bot está no canal de voz do usuário.

        Returns:
            VoiceClient conectado, ou None se não foi possível (já respondido)
        """
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ Este comando só funciona em servidores.", ephemeral=True
            )
            return None

        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            return voice_client

        if not (interaction.user.voice and interaction.user.voice.channel):
            await interaction.response.send_message(
                "❌ Entre num canal de voz primeiro!", ephemeral=True
            )
            return None

        try:
            return await interaction.user.voice.channel.connect()
        except (discord.ClientException, asyncio.TimeoutError) as e:
            logger.warning("Falha ao conectar no canal de voz: %s", e)
            await interaction.response.send_message(
                f"❌ Não consegui entrar no canal: {e}", ephemeral=True
            )
            return None

    # --- AUTOCOMPLETE PARA SFX ---

    async def sfx_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        """
        Fornece sugestões automáticas de sons disponíveis no soundboard.

        Args:
            interaction: Interação do Discord
            current: Texto atual digitado pelo usuário

        Returns:
            Lista de até 25 Choices com nomes dos sons
        """
        try:
            if not SOUNDS_DIR.is_dir():
                return []

            opcoes = sorted(
                f.stem
                for f in SOUNDS_DIR.iterdir()
                if f.is_file() and f.suffix.lower() in EXTENSOES_VALIDAS
            )

            termo = current.lower()
            # Discord limita a 25 opções de autocomplete
            return [
                app_commands.Choice(name=som, value=som)
                for som in opcoes
                if termo in som.lower()
            ][:25]
        except OSError:
            logger.debug("Falha ao listar sons para autocomplete", exc_info=True)
            return []

    # --- SLASH COMMANDS ---

    @app_commands.command(name="entrar", description="Entra no seu canal de voz")
    @app_commands.guild_only()
    async def entrar(self, interaction: discord.Interaction):
        """Conecta o bot no canal de voz do usuário."""
        if not (interaction.user.voice and interaction.user.voice.channel):
            return await interaction.response.send_message(
                "❌ Entre num canal de voz primeiro!", ephemeral=True
            )

        canal = interaction.user.voice.channel

        try:
            if interaction.guild.voice_client:
                await interaction.guild.voice_client.move_to(canal)
            else:
                await canal.connect()
        except (discord.ClientException, asyncio.TimeoutError) as e:
            return await interaction.response.send_message(
                f"❌ Não consegui entrar: {e}", ephemeral=True
            )

        await interaction.response.send_message(f"🔊 Plugado em: **{canal.name}**")

    @app_commands.command(name="sair", description="Sai do canal de voz")
    @app_commands.guild_only()
    async def sair(self, interaction: discord.Interaction):
        """Desconecta o bot do canal de voz."""
        if not interaction.guild.voice_client:
            return await interaction.response.send_message(
                "❌ Nem estou conectado.", ephemeral=True
            )

        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 Fui!")

    @app_commands.command(name="diga", description="Fala um texto em voz alta")
    @app_commands.describe(texto="O que eu devo falar?")
    @app_commands.guild_only()
    async def diga(self, interaction: discord.Interaction, texto: str):
        """Converte texto em fala e reproduz no canal de voz."""
        texto = texto.strip()
        if not texto:
            return await interaction.response.send_message(
                "❌ Preciso de um texto para falar.", ephemeral=True
            )

        voice_client = await self._garantir_conexao(interaction)
        if not voice_client:
            return

        await interaction.response.defer()

        caminho = None
        try:
            caminho = await self.gerar_tts(texto)
            await interaction.followup.send(f"🗣️ **Falando:** {texto[:MAX_TTS_CHARS]}")
            await self.reproduzir(voice_client, caminho, apagar_depois=True)
        except Exception as e:
            logger.error("Erro no comando /diga: %s", e, exc_info=True)
            if caminho:
                caminho.unlink(missing_ok=True)
            await interaction.followup.send(f"⚠️ Erro no áudio: {e}")

    @app_commands.command(name="sfx", description="Toca um efeito sonoro")
    @app_commands.describe(nome_som="Escolha o som da lista")
    @app_commands.autocomplete(nome_som=sfx_autocomplete)
    @app_commands.guild_only()
    async def sfx(self, interaction: discord.Interaction, nome_som: str):
        """Toca um efeito sonoro do soundboard."""
        caminho = resolver_som(SOUNDS_DIR, nome_som)
        if caminho is None:
            return await interaction.response.send_message(
                "❌ Som não encontrado.", ephemeral=True
            )

        voice_client = await self._garantir_conexao(interaction)
        if not voice_client:
            return

        await interaction.response.send_message(f"🎵 Play: **{caminho.stem}**")

        try:
            await self.reproduzir(voice_client, caminho)
        except Exception as e:
            logger.error("Erro no comando /sfx: %s", e, exc_info=True)
            await interaction.followup.send(f"⚠️ Erro no áudio: {e}")

    @app_commands.command(name="parar", description="Para qualquer som imediatamente")
    @app_commands.guild_only()
    async def parar(self, interaction: discord.Interaction):
        """Interrompe a reprodução atual."""
        voice_client = interaction.guild.voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await interaction.response.send_message("🛑 **Parei!**")
        else:
            await interaction.response.send_message(
                "😐 Silêncio total aqui.", ephemeral=True
            )

    async def cog_unload(self) -> None:
        """Remove arquivos de TTS que tenham sobrado."""
        for arquivo in TEMP_DIR.glob("tts_*.mp3"):
            arquivo.unlink(missing_ok=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Audio(bot))

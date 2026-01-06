"""
COG: ÁUDIO
==========

Gerencia todas as funcionalidades de áudio do bot:
- Text-to-Speech (TTS) em português brasileiro
- Efeitos sonoros (SFX) com autocomplete
- Conexão/desconexão de canais de voz
- Controle de reprodução

Dependências:
- edge-tts: Vozes naturais da Microsoft
- FFmpeg: Codificação de áudio
- PyNaCl: Criptografia de voz do Discord
"""

import discord
from discord import app_commands
from discord.ext import commands
import edge_tts
import os
import asyncio
from typing import Optional, List


class Audio(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voz_padrao = "pt-BR-AntonioNeural"

    # --- MÉTODOS AUXILIARES ---

    async def gerar_tts(self, texto: str) -> str:
        """
        Gera arquivo de áudio TTS a partir de texto.

        Utiliza Edge TTS da Microsoft para vozes naturais em PT-BR.

        Args:
            texto: Texto a ser convertido em fala

        Returns:
            str: Caminho do arquivo MP3 gerado (temp/fala.mp3)
        """
        caminho = "temp/fala.mp3"

        # Remove arquivo anterior se existir
        if os.path.exists(caminho):
            os.remove(caminho)

        # Gera novo áudio usando Edge TTS
        communicate = edge_tts.Communicate(texto, self.voz_padrao)
        await communicate.save(caminho)

        return caminho

    async def tocar_arquivo(self, interaction, caminho):
        if not interaction.guild.voice_client:
            return await interaction.followup.send("❌ Não estou conectado!")

        vc = interaction.guild.voice_client
        while vc.is_playing():
            await asyncio.sleep(0.1)

        try:
            source = discord.FFmpegPCMAudio(source=caminho, executable="ffmpeg")
            vc.play(source)
            while vc.is_playing():
                await asyncio.sleep(0.1)
        except Exception as e:
            await interaction.followup.send(f"⚠️ Erro no áudio: {e}")

    # --- AUTOCOMPLETE PARA SFX ---

    async def sfx_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        """
        Fornece sugestões automáticas de sons disponíveis no soundboard.

        Varre a pasta assets/sfx e retorna até 25 opções que correspondem
        ao que o usuário está digitando.

        Args:
            interaction: Interação do Discord
            current: Texto atual digitado pelo usuário

        Returns:
            Lista de até 25 Choices com nomes dos sons
        """
        try:
            arquivos = os.listdir("assets/sfx")
            opcoes = [f.replace(".mp3", "") for f in arquivos if f.endswith(".mp3")]

            # Filtra opções que contêm o texto digitado (case-insensitive)
            return [
                app_commands.Choice(name=som, value=som)
                for som in opcoes
                if current.lower() in som.lower()
            ][
                :25
            ]  # Discord limita a 25 opções de autocomplete
        except Exception:
            return []  # Retorna vazio se houver erro (ex: pasta não existe)

    # --- SLASH COMMANDS ---
    @app_commands.command(name="entrar", description="Entra no seu canal de voz")
    async def entrar(self, interaction: discord.Interaction):
        if interaction.user.voice:
            channel = interaction.user.voice.channel
            await channel.connect()
            await interaction.response.send_message(
                f"🔊 Plugado em: **{channel.name}**"
            )
        else:
            await interaction.response.send_message(
                "❌ Entre num canal de voz primeiro!", ephemeral=True
            )

    @app_commands.command(name="sair", description="Sai do canal de voz")
    async def sair(self, interaction: discord.Interaction):
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("👋 Fui!")
        else:
            await interaction.response.send_message(
                "❌ Nem estou conectado.", ephemeral=True
            )

    @app_commands.command(name="diga", description="Fala um texto em voz alta")
    @app_commands.describe(texto="O que eu devo falar?")
    async def diga(self, interaction: discord.Interaction, texto: str):
        if not interaction.guild.voice_client:
            if interaction.user.voice:
                await interaction.user.voice.channel.connect()
            else:
                return await interaction.response.send_message(
                    "❌ Entre num canal de voz!", ephemeral=True
                )

        await interaction.response.defer()  # Avisa que vai processar
        await interaction.followup.send(f"🗣️ **Falando:** {texto}")

        arquivo = await self.gerar_tts(texto)
        await self.tocar_arquivo(interaction, arquivo)

    @app_commands.command(name="sfx", description="Toca um efeito sonoro")
    @app_commands.describe(nome_som="Escolha o som da lista")
    @app_commands.autocomplete(nome_som=sfx_autocomplete)  # <--- MÁGICA AQUI
    async def sfx(self, interaction: discord.Interaction, nome_som: str):
        caminho = f"assets/sfx/{nome_som}.mp3"
        if not os.path.exists(caminho):
            return await interaction.response.send_message(
                "❌ Som não encontrado.", ephemeral=True
            )

        if not interaction.guild.voice_client:
            if interaction.user.voice:
                await interaction.user.voice.channel.connect()
            else:
                return await interaction.response.send_message(
                    "❌ Entre na call!", ephemeral=True
                )

        await interaction.response.send_message(f"🎵 Play: **{nome_som}**")
        await self.tocar_arquivo(interaction, caminho)

    @app_commands.command(name="parar", description="Para qualquer som imediatamente")
    async def parar(self, interaction: discord.Interaction):
        if (
            interaction.guild.voice_client
            and interaction.guild.voice_client.is_playing()
        ):
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("🛑 **Parei!**")
        else:
            await interaction.response.send_message(
                "😐 Silêncio total aqui.", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Audio(bot))

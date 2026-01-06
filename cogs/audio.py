import discord
from discord import app_commands
from discord.ext import commands
import edge_tts
import os
import asyncio

class Audio(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voz_padrao = "pt-BR-AntonioNeural"

    # --- AUXILIARES ---
    async def gerar_tts(self, texto):
        caminho = "temp/fala.mp3"
        if os.path.exists(caminho): os.remove(caminho)
        communicate = edge_tts.Communicate(texto, self.voz_padrao)
        await communicate.save(caminho)
        return caminho

    async def tocar_arquivo(self, interaction, caminho):
        if not interaction.guild.voice_client:
            return await interaction.followup.send("❌ Não estou conectado!")
            
        vc = interaction.guild.voice_client
        while vc.is_playing(): await asyncio.sleep(0.1)

        try:
            source = discord.FFmpegPCMAudio(source=caminho, executable="ffmpeg")
            vc.play(source)
            while vc.is_playing(): await asyncio.sleep(0.1)
        except Exception as e:
            await interaction.followup.send(f"⚠️ Erro no áudio: {e}")

    # --- AUTOCOMPLETE PARA SFX ---
    async def sfx_autocomplete(self, interaction: discord.Interaction, current: str):
        try:
            arquivos = os.listdir("assets/sfx")
            opcoes = [f.replace(".mp3", "") for f in arquivos if f.endswith(".mp3")]
            # Filtra o que o usuário está digitando
            return [
                app_commands.Choice(name=som, value=som)
                for som in opcoes if current.lower() in som.lower()
            ][:25] # Limite do Discord é 25 opções
        except: return []

    # --- SLASH COMMANDS ---
    @app_commands.command(name="entrar", description="Entra no seu canal de voz")
    async def entrar(self, interaction: discord.Interaction):
        if interaction.user.voice:
            channel = interaction.user.voice.channel
            await channel.connect()
            await interaction.response.send_message(f"🔊 Plugado em: **{channel.name}**")
        else:
            await interaction.response.send_message("❌ Entre num canal de voz primeiro!", ephemeral=True)

    @app_commands.command(name="sair", description="Sai do canal de voz")
    async def sair(self, interaction: discord.Interaction):
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("👋 Fui!")
        else:
            await interaction.response.send_message("❌ Nem estou conectado.", ephemeral=True)

    @app_commands.command(name="diga", description="Fala um texto em voz alta")
    @app_commands.describe(texto="O que eu devo falar?")
    async def diga(self, interaction: discord.Interaction, texto: str):
        if not interaction.guild.voice_client:
            if interaction.user.voice:
                await interaction.user.voice.channel.connect()
            else:
                return await interaction.response.send_message("❌ Entre num canal de voz!", ephemeral=True)

        await interaction.response.defer() # Avisa que vai processar
        await interaction.followup.send(f"🗣️ **Falando:** {texto}")
        
        arquivo = await self.gerar_tts(texto)
        await self.tocar_arquivo(interaction, arquivo)

    @app_commands.command(name="sfx", description="Toca um efeito sonoro")
    @app_commands.describe(nome_som="Escolha o som da lista")
    @app_commands.autocomplete(nome_som=sfx_autocomplete) # <--- MÁGICA AQUI
    async def sfx(self, interaction: discord.Interaction, nome_som: str):
        caminho = f"assets/sfx/{nome_som}.mp3"
        if not os.path.exists(caminho):
            return await interaction.response.send_message("❌ Som não encontrado.", ephemeral=True)
            
        if not interaction.guild.voice_client:
            if interaction.user.voice: await interaction.user.voice.channel.connect()
            else: return await interaction.response.send_message("❌ Entre na call!", ephemeral=True)

        await interaction.response.send_message(f"🎵 Play: **{nome_som}**")
        await self.tocar_arquivo(interaction, caminho)

    @app_commands.command(name="parar", description="Para qualquer som imediatamente")
    async def parar(self, interaction: discord.Interaction):
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("🛑 **Parei!**")
        else:
            await interaction.response.send_message("😐 Silêncio total aqui.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Audio(bot))
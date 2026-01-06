import discord
from discord import app_commands
from discord.ext import commands
import google.generativeai as genai
import os
import random

MODEL_NAME = "gemini-2.5-flash"

class Iconico(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)

    async def gerar_texto(self, prompt):
        try:
            model = genai.GenerativeModel(MODEL_NAME)
            response = model.generate_content(prompt)
            return response.text
        except Exception:
            return "Minha criatividade pifou. Tente de novo."

    @app_commands.command(name="rpg", description="Gera uma ficha de RPG zueira")
    async def rpg(self, interaction: discord.Interaction, usuario: discord.Member = None):
        if not usuario: usuario = interaction.user
        await interaction.response.defer()

        prompt = f"Crie uma ficha de RPG engraçada para {usuario.name}. Classe bizarra, Poder aleatório, Fraqueza ridícula. Use emojis e formate como lista."
        texto = await self.gerar_texto(prompt)
        
        embed = discord.Embed(title=f"⚔️ Ficha: {usuario.name}", description=texto, color=discord.Color.red())
        embed.set_thumbnail(url=usuario.display_avatar.url)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="vibe", description="Julga a vibe da call (com áudio!)")
    async def vibe(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Entre na call primeiro!", ephemeral=True)
            
        await interaction.response.defer()
        
        # Escolhe vítima aleatória
        vitima = random.choice(interaction.user.voice.channel.members)
        prompt = f"Julgue a vibe de {vitima.name} de forma ácida e engraçada (máx 2 frases)."
        texto = await self.gerar_texto(prompt)
        
        embed = discord.Embed(description=f"🗣️ **{texto}**", color=discord.Color.magenta())
        embed.set_author(name=f"Juiz de Vibe: {vitima.name}", icon_url=vitima.display_avatar.url)
        await interaction.followup.send(embed=embed)

        # Fala em áudio
        audio_cog = self.bot.get_cog('Audio')
        if audio_cog:
            if not interaction.guild.voice_client: 
                await interaction.user.voice.channel.connect()
            arquivo = await audio_cog.gerar_tts(texto)
            await audio_cog.tocar_arquivo(interaction, arquivo)

    @app_commands.command(name="shipp", description="Analisa compatibilidade de casal")
    async def shipp(self, interaction: discord.Interaction, pessoa1: discord.Member, pessoa2: discord.Member = None):
        if not pessoa2: pessoa2 = interaction.user
        await interaction.response.defer()

        prompt = f"Aja como cupido. Calcule a compatibilidade entre {pessoa1.name} e {pessoa2.name}. Dê nota % e motivo engraçado."
        texto = await self.gerar_texto(prompt)
        
        embed = discord.Embed(title="💘 Análise do Cupido", description=texto, color=discord.Color.pink())
        await interaction.followup.send(f"{pessoa1.mention} + {pessoa2.mention}", embed=embed)

async def setup(bot):
    await bot.add_cog(Iconico(bot))
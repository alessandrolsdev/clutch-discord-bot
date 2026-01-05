import discord
from discord.ext import commands
import google.generativeai as genai
import os
import random

class Iconico(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)

    # --- FUNÇÃO AUXILIAR DE IA ---
    async def gerar_texto(self, prompt):
        try:
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            return "Minha criatividade pifou. Tente de novo."

    # --- 1. RPG DO SERVIDOR ---
    @commands.command()
    async def rpg(self, ctx, usuario: discord.Member = None):
        """Cria uma ficha de RPG engraçada para o usuário"""
        if not usuario: usuario = ctx.author

        prompt = (f"Crie uma ficha de personagem de RPG super engraçada e criativa para '{usuario.name}'. "
                  f"Invente: Uma Classe bizarra (ex: Mago da Preguiça), Nível de Poder (número aleatório), "
                  f"Uma Fraqueza ridícula e uma Habilidade Especial inútil ou caótica. "
                  f"Use emojis. Seja breve e formate como uma lista.")

        async with ctx.typing():
            texto = await self.gerar_texto(prompt)
            
            # Monta o cartão visual
            embed = discord.Embed(title=f"⚔️ Ficha: {usuario.name}", description=texto, color=discord.Color.red())
            embed.set_thumbnail(url=usuario.display_avatar.url)
            await ctx.send(embed=embed)

    # --- 2. DETETIVE DE VIBE (Fala em Áudio!) ---
    @commands.command()
    async def vibe(self, ctx):
        """Julga a vibe de alguém na call e FALTA MAL em áudio"""
        if not ctx.author.voice:
            return await ctx.send("❌ Entre numa call para eu sentir a vibe!")

        # Escolhe uma vítima aleatória do canal de voz
        membros = ctx.author.voice.channel.members
        vitima = random.choice(membros)

        prompt = (f"Aja como um juiz de 'Vibes' sarcástico e engraçado. "
                  f"Analise a energia do usuário '{vitima.name}' hoje. "
                  f"Dê um veredito curto (máximo 2 frases) dizendo se a vibe é boa, tóxica, de corno, de rico, etc. "
                  f"Seja criativo e ácido.")

        async with ctx.typing():
            texto = await self.gerar_texto(prompt)
            await ctx.send(f"🔮 **Lendo a aura de {vitima.mention}...**\n🗣️ _{texto}_")

            # Manda o Áudio falar
            audio_cog = self.bot.get_cog('Audio')
            if audio_cog:
                # Gera o áudio da zueira
                arquivo = await audio_cog.gerar_tts(texto)
                # Toca sem dó
                await audio_cog.tocar_arquivo(ctx, arquivo)

    # --- 3. SHIPPADOR TÓXICO ---
    @commands.command()
    async def shipp(self, ctx, user1: discord.Member, user2: discord.Member = None):
        """Analisa o casal e diz se dá namoro ou BO"""
        if not user2: user2 = ctx.author # Se marcar só um, shippa com quem chamou

        prompt = (f"Aja como um cupido bêbado e sincero. Analise o casal '{user1.name}' e '{user2.name}'. "
                  f"Dê uma nota de compatibilidade de 0 a 100%. "
                  f"Explique o motivo da nota de forma engraçada (ex: eles combinam pq ambos são trouxas).")

        async with ctx.typing():
            texto = await self.gerar_texto(prompt)
            
            embed = discord.Embed(title=f"💘 Análise de Casal", description=texto, color=discord.Color.purple())
            # Tenta colocar as duas fotos lado a lado (gambiarra visual)
            embed.set_thumbnail(url="https://i.imgur.com/5bZ8u2i.png") # Coração pixel art
            await ctx.send(f"{user1.mention} + {user2.mention}", embed=embed)

async def setup(bot):
    await bot.add_cog(Iconico(bot))
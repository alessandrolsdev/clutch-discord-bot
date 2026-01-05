import discord
from discord.ext import commands
import google.generativeai as genai
import os

class Cerebro(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv("GEMINI_API_KEY")
        
        # Configura a IA
        if self.api_key:
            genai.configure(api_key=self.api_key)
        else:
            print("⚠️ AVISO: GEMINI_API_KEY não encontrada no .env")
        
        # Dicionário de Personalidades
        self.personas = {
            "padrao": "Você é o Clutch, um assistente robótico útil, breve e levemente sarcástico.",
            "coach": "Você é um Coach de crossfit intenso. GRITE (use Caps Lock), use gírias de academia, seja agressivo e motivador.",
            "tio": "Você é o Tio do Pavê brasileiro. Faça trocadilhos ruins com tudo o que disserem. Ria alto (KKKKK).",
            "hacker": "Você é um especialista em cibersegurança paranoico. Fale sobre IPs, firewalls, matrix e conspirações.",
            "poeta": "Você é um poeta dramático do século 19. Fale com palavras difíceis e faça rimas."
        }
        self.persona_atual = "padrao"

    @commands.command()
    async def incorporar(self, ctx, persona):
        """Muda a personalidade da IA"""
        persona = persona.lower()
        if persona in self.personas:
            self.persona_atual = persona
            await ctx.send(f"🔄 Personalidade carregada: **{persona.upper()}**")
        else:
            opcoes = ", ".join(self.personas.keys())
            await ctx.send(f"❌ Persona inválida. Opções: `{opcoes}`")

    @commands.command(aliases=['c'])
    async def clutch(self, ctx, *, pergunta):
        """Conversa com a IA e responde em áudio"""
        if not self.api_key:
            return await ctx.send("❌ Configure a API Key no .env")

        # Prepara o prompt com a persona
        instrucao = self.personas.get(self.persona_atual)
        prompt_final = f"{instrucao}\n\nO usuário disse: '{pergunta}'\n(Responda de forma curta para ser falado em áudio, máximo 2 frases)."

        async with ctx.typing():
            try:
                # Usando gemini-pro que é mais estável
                model = genai.GenerativeModel('gemini-2.5-flash')
                response = model.generate_content(prompt_final)
                texto_resposta = response.text
                
                # Manda no chat
                await ctx.send(f"🤖 **{self.persona_atual.capitalize()}:** {texto_resposta}")
                
                # Mágica: Chama o módulo de Áudio para falar
                audio_cog = self.bot.get_cog('Audio')
                if audio_cog:
                    arquivo = await audio_cog.gerar_tts(texto_resposta)
                    await audio_cog.tocar_arquivo(ctx, arquivo)
                else:
                    await ctx.send("⚠️ Módulo de áudio não encontrado para falar a resposta.")
                    
            except Exception as e:
                await ctx.send(f"❌ Erro na IA: {e}")

    @commands.command()
    async def batalha(self, ctx, *, oponentes):
        """Simula uma luta épica entre duas coisas"""
        prompt = (f"Atue como um narrador de lutas do UFC muito empolgado. "
                  f"Analise quem ganharia esta luta: '{oponentes}'. "
                  f"Descreva o final da luta de forma resumida e dê o veredito do vencedor.")
        
        async with ctx.typing():
            try:
                model = genai.GenerativeModel('gemini-2.5-flash')
                response = model.generate_content(prompt)
                texto = response.text
                
                await ctx.send(f"🥊 **ARENA CLUTCH:**\n{texto}")
            except Exception as e:
                await ctx.send(f"❌ Erro na batalha: {e}")

# Função obrigatória para carregar o módulo
async def setup(bot):
    await bot.add_cog(Cerebro(bot))
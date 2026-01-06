import discord
from discord import app_commands
from discord.ext import commands
import google.generativeai as genai
import os
from collections import deque

# ⚡ MODELO DE PONTA
MODEL_NAME = "gemini-2.5-flash"

class Cerebro(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
        
        # Memória: Guarda as últimas 5 mensagens de cada usuário
        self.historico = {}

        self.personas = {
            "padrao": "Você é o Clutch. Responda de forma curta, inteligente e útil.",
            "coach": "Você é um Coach motivacional intenso. USE CAPS LOCK e emojis de força 💪.",
            "hacker": "Você é um especialista em Cybersegurança. Use termos técnicos e seja misterioso 🕶️.",
            "fofoqueira": "Você é uma vizinha fofoqueira que sabe de tudo. Use gírias e 'menina do céu' 💅."
        }
        self.persona_atual = "padrao"

    def get_historico(self, user_id):
        if user_id not in self.historico:
            self.historico[user_id] = deque(maxlen=5)
        return self.historico[user_id]

    @app_commands.command(name="persona", description="Muda a personalidade da IA")
    @app_commands.choices(persona=[
        app_commands.Choice(name="🤖 Padrão", value="padrao"),
        app_commands.Choice(name="🏋️ Coach", value="coach"),
        app_commands.Choice(name="🕶️ Hacker", value="hacker"),
        app_commands.Choice(name="💅 Fofoqueira", value="fofoqueira")
    ])
    async def persona(self, interaction: discord.Interaction, persona: app_commands.Choice[str]):
        self.persona_atual = persona.value
        
        embed = discord.Embed(
            title="🔄 Personalidade Atualizada", 
            description=f"Modo ativado: **{persona.name}**", 
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="chat", description="Conversa contínua com a IA")
    @app_commands.describe(mensagem="Sua mensagem para o bot")
    async def chat(self, interaction: discord.Interaction, mensagem: str):
        if not self.api_key: 
            return await interaction.response.send_message("❌ API Key não configurada.", ephemeral=True)
        
        await interaction.response.defer()

        # Constrói o histórico para a IA ter contexto
        history = self.get_historico(interaction.user.id)
        history_text = "\n".join(history)
        
        instrucao = self.personas.get(self.persona_atual)
        prompt = f"{instrucao}\n\n[Histórico Recente]:\n{history_text}\n\n[Usuário]: {mensagem}\n(Responda de forma concisa)"

        try:
            model = genai.GenerativeModel(MODEL_NAME)
            response = model.generate_content(prompt)
            texto_resposta = response.text
            
            # Atualiza memória
            history.append(f"User: {mensagem}")
            history.append(f"Bot: {texto_resposta}")

            # Embed Elegante
            embed = discord.Embed(description=texto_resposta, color=discord.Color.blue())
            embed.set_author(name=f"{self.persona_atual.capitalize()} Bot", icon_url=self.bot.user.display_avatar.url)
            embed.set_footer(text=f"Modelo: {MODEL_NAME} • Pedido por {interaction.user.name}")
            
            await interaction.followup.send(embed=embed)
            
            # Integração com Áudio (se disponível)
            audio_cog = self.bot.get_cog('Audio')
            if audio_cog and interaction.guild.voice_client:
                arquivo = await audio_cog.gerar_tts(texto_resposta)
                await audio_cog.tocar_arquivo(interaction, arquivo)

        except Exception as e:
            await interaction.followup.send(f"❌ Erro de processamento: {e}")

async def setup(bot):
    await bot.add_cog(Cerebro(bot))
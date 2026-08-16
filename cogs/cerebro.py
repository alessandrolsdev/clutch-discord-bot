"""
COG: CÉREBRO (CHAT COM IA)
==========================

Chat contextual com o Google Gemini.

Notas de implementação:
- A persona é guardada **por servidor**, não globalmente: antes, qualquer
  usuário trocando a persona afetava todos os servidores ao mesmo tempo.
- O histórico é por (servidor, usuário) e limitado, evitando vazar conversa de
  um usuário no contexto de outro.
- As chamadas ao Gemini rodam fora do event loop (ver utils/ai.py).
"""

from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import settings
from utils.ai import gemini
from utils.logger import get_logger

logger = get_logger(__name__)

PERSONAS: Dict[str, str] = {
    "padrao": "Você é o Clutch. Responda de forma curta, inteligente e útil.",
    "coach": "Você é um Coach motivacional intenso. USE CAPS LOCK e emojis de força 💪.",
    "hacker": "Você é um especialista em Cybersegurança. Use termos técnicos e seja misterioso 🕶️.",
    "fofoqueira": "Você é uma vizinha fofoqueira que sabe de tudo. Use gírias e 'menina do céu' 💅.",
}


class Cerebro(commands.Cog):
    """Cog de conversa com IA."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # (guild_id, user_id) -> últimas trocas de mensagem
        self.historico: Dict[Tuple[int, int], Deque[str]] = defaultdict(
            lambda: deque(maxlen=settings.ai.history_size * 2)
        )
        # guild_id -> persona ativa naquele servidor
        self.persona_por_guild: Dict[int, str] = defaultdict(lambda: "padrao")

    def _chave(self, interaction: discord.Interaction) -> Tuple[int, int]:
        """Chave de histórico isolada por servidor e usuário."""
        guild_id = interaction.guild.id if interaction.guild else 0
        return (guild_id, interaction.user.id)

    def _persona(self, interaction: discord.Interaction) -> str:
        """Persona ativa no contexto atual."""
        guild_id = interaction.guild.id if interaction.guild else 0
        return self.persona_por_guild[guild_id]

    @app_commands.command(name="persona", description="Muda a personalidade da IA")
    @app_commands.choices(
        persona=[
            app_commands.Choice(name="🤖 Padrão", value="padrao"),
            app_commands.Choice(name="🏋️ Coach", value="coach"),
            app_commands.Choice(name="🕶️ Hacker", value="hacker"),
            app_commands.Choice(name="💅 Fofoqueira", value="fofoqueira"),
        ]
    )
    async def persona(
        self, interaction: discord.Interaction, persona: app_commands.Choice[str]
    ):
        """Troca a persona da IA neste servidor."""
        guild_id = interaction.guild.id if interaction.guild else 0
        self.persona_por_guild[guild_id] = persona.value

        embed = discord.Embed(
            title="🔄 Personalidade Atualizada",
            description=f"Modo ativado: **{persona.name}**",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="chat", description="Conversa contínua com a IA")
    @app_commands.describe(mensagem="Sua mensagem para o bot")
    # Rate limit por usuário: cada chamada custa cota do Gemini
    @app_commands.checks.cooldown(3, 60.0, key=lambda i: i.user.id)
    async def chat(self, interaction: discord.Interaction, mensagem: str):
        """Conversa com a IA mantendo contexto recente."""
        if not gemini.is_enabled:
            return await interaction.response.send_message(
                "❌ IA não configurada (defina GEMINI_API_KEY).", ephemeral=True
            )

        mensagem = mensagem.strip()
        if not mensagem:
            return await interaction.response.send_message(
                "❌ Mande alguma coisa para eu responder.", ephemeral=True
            )

        await interaction.response.defer()

        historico = self.historico[self._chave(interaction)]
        instrucao = PERSONAS[self._persona(interaction)]
        prompt = (
            f"{instrucao}\n\n"
            f"[Histórico Recente]:\n{chr(10).join(historico)}\n\n"
            f"[Usuário]: {mensagem}\n(Responda de forma concisa)"
        )

        texto_resposta = await gemini.gerar(prompt)
        if not texto_resposta:
            return await interaction.followup.send(
                "❌ Não consegui responder agora. Tente de novo em instantes."
            )

        # Atualiza memória só quando houve resposta de verdade
        historico.append(f"User: {mensagem}")
        historico.append(f"Bot: {texto_resposta}")

        embed = discord.Embed(
            description=texto_resposta, color=discord.Color.blue()
        )
        embed.set_author(
            name=f"{self._persona(interaction).capitalize()} Bot",
            icon_url=self.bot.user.display_avatar.url,
        )
        embed.set_footer(
            text=f"Modelo: {gemini.model_name} • Pedido por {interaction.user.display_name}"
        )

        await interaction.followup.send(embed=embed)

        # Integração com Áudio: só fala se o bot já estiver numa call
        audio_cog = self.bot.get_cog("Audio")
        if audio_cog and interaction.guild and interaction.guild.voice_client:
            try:
                await audio_cog.falar(interaction.guild, texto_resposta)
            except Exception as e:
                logger.warning("Falha ao reproduzir TTS da resposta: %s", e)

    @app_commands.command(name="esquecer", description="Limpa sua conversa com a IA")
    async def esquecer(self, interaction: discord.Interaction):
        """Apaga o histórico de conversa do usuário neste servidor."""
        self.historico.pop(self._chave(interaction), None)
        await interaction.response.send_message(
            "🧹 Memória limpa! Começamos do zero.", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Cerebro(bot))

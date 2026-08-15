"""
COG: ICÔNICO (COMANDOS DE ZUEIRA COM IA)
========================================

Comandos de entretenimento gerados pelo Gemini: ficha de RPG, julgamento de
vibe da call e teste de compatibilidade.

As chamadas de IA passam por utils/ai.py (não bloqueiam o event loop).
"""

import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.ai import gemini
from utils.logger import get_logger

logger = get_logger(__name__)

MSG_IA_INDISPONIVEL = "Minha criatividade pifou. Tente de novo."


class Iconico(commands.Cog):
    """Cog de comandos divertidos com IA."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def gerar_texto(self, prompt: str) -> str:
        """Gera texto com fallback amigável quando a IA falha."""
        return await gemini.gerar(prompt) or MSG_IA_INDISPONIVEL

    async def _checar_ia(self, interaction: discord.Interaction) -> bool:
        """Responde e retorna False se a IA não estiver configurada."""
        if gemini.is_enabled:
            return True
        await interaction.response.send_message(
            "❌ IA não configurada (defina GEMINI_API_KEY).", ephemeral=True
        )
        return False

    @app_commands.command(name="rpg", description="Gera uma ficha de RPG zueira")
    @app_commands.describe(usuario="De quem é a ficha? (padrão: você)")
    async def rpg(
        self,
        interaction: discord.Interaction,
        usuario: Optional[discord.Member] = None,
    ):
        """Gera uma ficha de RPG cômica para um membro."""
        if not await self._checar_ia(interaction):
            return

        alvo = usuario or interaction.user
        await interaction.response.defer()

        prompt = (
            f"Crie uma ficha de RPG engraçada para {alvo.display_name}. "
            "Classe bizarra, Poder aleatório, Fraqueza ridícula. "
            "Use emojis e formate como lista. Mantenha leve e sem ofensas pessoais."
        )
        texto = await self.gerar_texto(prompt)

        embed = discord.Embed(
            title=f"⚔️ Ficha: {alvo.display_name}",
            description=texto,
            color=discord.Color.red(),
        )
        embed.set_thumbnail(url=alvo.display_avatar.url)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="vibe", description="Julga a vibe da call (com áudio!)")
    @app_commands.guild_only()
    async def vibe(self, interaction: discord.Interaction):
        """Escolhe alguém da call e julga a vibe, falando em áudio se possível."""
        if not await self._checar_ia(interaction):
            return

        if not (interaction.user.voice and interaction.user.voice.channel):
            return await interaction.response.send_message(
                "❌ Entre na call primeiro!", ephemeral=True
            )

        canal = interaction.user.voice.channel
        # Ignora bots — antes o próprio Clutch podia ser sorteado como "vítima"
        candidatos = [m for m in canal.members if not m.bot]
        if not candidatos:
            return await interaction.response.send_message(
                "❌ Não tem ninguém para julgar aqui.", ephemeral=True
            )

        await interaction.response.defer()

        vitima = random.choice(candidatos)
        prompt = (
            f"Julgue a vibe de {vitima.display_name} de forma ácida e engraçada, "
            "sem xingamentos e sem ofensas pessoais reais (máx 2 frases)."
        )
        texto = await self.gerar_texto(prompt)

        embed = discord.Embed(
            description=f"🗣️ **{texto}**", color=discord.Color.magenta()
        )
        embed.set_author(
            name=f"Juiz de Vibe: {vitima.display_name}",
            icon_url=vitima.display_avatar.url,
        )
        await interaction.followup.send(embed=embed)

        # Fala em áudio se o bot já estiver conectado na call
        audio_cog = self.bot.get_cog("Audio")
        if audio_cog and interaction.guild.voice_client:
            try:
                await audio_cog.falar(interaction.guild, texto)
            except Exception as e:
                logger.warning("Falha ao reproduzir TTS do /vibe: %s", e)

    @app_commands.command(name="shipp", description="Analisa compatibilidade de casal")
    @app_commands.describe(
        pessoa1="Primeira pessoa", pessoa2="Segunda pessoa (padrão: você)"
    )
    async def shipp(
        self,
        interaction: discord.Interaction,
        pessoa1: discord.Member,
        pessoa2: Optional[discord.Member] = None,
    ):
        """Calcula uma compatibilidade fictícia entre dois membros."""
        if not await self._checar_ia(interaction):
            return

        alvo2 = pessoa2 or interaction.user
        if pessoa1.id == alvo2.id:
            return await interaction.response.send_message(
                "❌ Preciso de duas pessoas diferentes!", ephemeral=True
            )

        await interaction.response.defer()

        prompt = (
            "Aja como cupido. Calcule a compatibilidade entre "
            f"{pessoa1.display_name} e {alvo2.display_name}. "
            "Dê nota em % e um motivo engraçado e respeitoso."
        )
        texto = await self.gerar_texto(prompt)

        embed = discord.Embed(
            title="💘 Análise do Cupido",
            description=texto,
            color=discord.Color.pink(),
        )
        await interaction.followup.send(
            f"{pessoa1.mention} + {alvo2.mention}",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                everyone=False, roles=False, users=[pessoa1, alvo2]
            ),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Iconico(bot))

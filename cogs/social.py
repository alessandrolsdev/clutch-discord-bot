"""
COG: SOCIAL (GAMIFICAÇÃO)
==========================

Sistema completo de gamificação para engajamento de membros:

**Sistema de XP:**
- +XP por mensagem enviada (com cooldown anti-spam)
- +XP por minuto em canal de voz
- Level up ao atingir (level * multiplicador) XP; o excedente é mantido

**Sistema de Streak:**
- Rastreia dias consecutivos ativos
- Incrementa se enviar mensagem em dias seguidos
- Reseta se ficar mais de 1 dia sem atividade

**Sistema de Conquistas (Badges):**
- "👶 Novato": Primeira mensagem
- "🔥 On Fire": 7 dias de streak
- "💎 VIP": Nível 10+
- "🎙️ Podcaster": 600+ minutos de voz

**Perfil Customizável:**
- Bio personalizada (até 100 caracteres)
- Card visual com progresso de XP
- Exibição de todas as conquistas
"""

import time
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from config.settings import settings
from infra.database import get_conexao
from utils.ai import gemini
from utils.logger import get_logger

logger = get_logger(__name__)

BADGE_NOVATO = "👶 Novato"
BADGE_ON_FIRE = "🔥 On Fire"
BADGE_VIP = "💎 VIP"
BADGE_PODCASTER = "🎙️ Podcaster"

MINUTOS_PARA_PODCASTER = 600
STREAK_PARA_ON_FIRE = 7
LEVEL_PARA_VIP = 10


class Social(commands.Cog):
    """Cog de XP, níveis, streaks e conquistas."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = settings.gamification
        self.voice_sessions: Dict[int, float] = {}
        # user_id -> timestamp do último ganho de XP (cooldown anti-spam)
        self.xp_cooldown: Dict[int, float] = {}

    # --- MÉTODOS AUXILIARES DE BANCO DE DADOS ---

    async def get_user_data(
        self, user_id: int, user_name: str
    ) -> Tuple[aiosqlite.Row, List[str]]:
        """
        Busca ou cria dados de um usuário no banco.

        Se o usuário não existir, cria um registro com valores padrão.

        Args:
            user_id: ID do Discord do usuário
            user_name: Nome de exibição do usuário

        Returns:
            Tupla contendo:
            - user (Row): Dados do usuário (xp, level, streak, etc)
            - badges (List[str]): Lista de badges conquistados
        """
        async with get_conexao() as db:
            # INSERT idempotente: evita a corrida entre SELECT e INSERT quando
            # duas mensagens do mesmo usuário chegam quase juntas.
            await db.execute(
                "INSERT INTO usuarios (id, nome) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET nome = excluded.nome",
                (user_id, user_name),
            )
            await db.commit()

            async with db.execute(
                "SELECT * FROM usuarios WHERE id = ?", (user_id,)
            ) as cursor:
                user = await cursor.fetchone()

            async with db.execute(
                "SELECT badge_name FROM conquistas WHERE user_id = ?", (user_id,)
            ) as cursor:
                badges = [row["badge_name"] for row in await cursor.fetchall()]

        return user, badges

    async def add_badge(self, user_id: int, badge_name: str) -> bool:
        """
        Concede uma medalha ao usuário.

        Args:
            user_id: ID do Discord do usuário
            badge_name: Nome da medalha

        Returns:
            True se a medalha foi concedida agora (False se já tinha)
        """
        hoje = date.today().isoformat()
        async with get_conexao() as db:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO conquistas (user_id, badge_name, data_conquista) "
                "VALUES (?, ?, ?)",
                (user_id, badge_name, hoje),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def anunciar_badge(
        self,
        channel: Optional[discord.abc.Messageable],
        user_id: int,
        user_mention: str,
        badge_name: str,
    ) -> None:
        """Concede a medalha e anuncia no canal apenas se for inédita."""
        if not await self.add_badge(user_id, badge_name):
            return

        if channel is None:
            return

        embed = discord.Embed(
            title="🏆 CONQUISTA!",
            description=f"Parabéns {user_mention}, você ganhou a medalha **{badge_name}**!",
            color=discord.Color.gold(),
        )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            logger.warning("Não foi possível anunciar conquista: %s", e)

    def _calcular_streak(self, streak: int, last_date: Optional[str]) -> int:
        """
        Calcula o novo streak com base na data da última mensagem.

        Args:
            streak: Streak atual
            last_date: Data da última mensagem (YYYY-MM-DD) ou None

        Returns:
            Novo valor do streak
        """
        hoje = date.today()
        if not last_date:
            return 1

        try:
            anterior = datetime.strptime(last_date, "%Y-%m-%d").date()
        except ValueError:
            # Data corrompida no banco: recomeça o streak em vez de quebrar
            logger.warning("Data inválida no banco: %r", last_date)
            return 1

        dias = (hoje - anterior).days
        if dias == 0:
            return streak  # Já contabilizado hoje
        if dias == 1:
            return streak + 1
        return 1  # Quebrou o streak

    # --- LISTENERS ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Concede XP por mensagem, respeitando o cooldown anti-spam."""
        if message.author.bot or not message.guild:
            return  # Ignora bots e DMs

        agora = time.time()
        ultimo = self.xp_cooldown.get(message.author.id, 0)
        if agora - ultimo < self.config.xp_cooldown:
            return  # Ainda em cooldown: nada de XP nem escrita no banco

        self.xp_cooldown[message.author.id] = agora

        user, _ = await self.get_user_data(message.author.id, message.author.name)

        novo_xp = user["xp"] + self.config.xp_per_message
        msg_count = user["msg_count"] + 1
        level = user["level"]
        hoje = date.today().isoformat()
        streak = self._calcular_streak(user["streak"], user["last_msg_date"])

        # Level up: mantém o XP excedente em vez de zerar o progresso
        subiu_de_nivel = False
        while novo_xp >= level * self.config.level_up_multiplier:
            novo_xp -= level * self.config.level_up_multiplier
            level += 1
            subiu_de_nivel = True

        async with get_conexao() as db:
            await db.execute(
                "UPDATE usuarios SET xp=?, msg_count=?, streak=?, last_msg_date=?, "
                "level=?, nome=? WHERE id=?",
                (
                    novo_xp,
                    msg_count,
                    streak,
                    hoje,
                    level,
                    message.author.name,
                    message.author.id,
                ),
            )
            await db.commit()

        if subiu_de_nivel:
            try:
                await message.channel.send(
                    f"🎉 **LEVEL UP!** {message.author.mention} subiu para o **Nível {level}**!"
                )
            except discord.HTTPException as e:
                logger.warning("Não foi possível anunciar level up: %s", e)

        # Conquistas
        await self.anunciar_badge(
            message.channel, message.author.id, message.author.mention, BADGE_NOVATO
        )
        if streak >= STREAK_PARA_ON_FIRE:
            await self.anunciar_badge(
                message.channel,
                message.author.id,
                message.author.mention,
                BADGE_ON_FIRE,
            )
        if level >= LEVEL_PARA_VIP:
            await self.anunciar_badge(
                message.channel, message.author.id, message.author.mention, BADGE_VIP
            )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Contabiliza minutos em call e concede XP ao sair."""
        if member.bot:
            return

        entrou = before.channel is None and after.channel is not None
        saiu = before.channel is not None and after.channel is None

        if entrou:
            self.voice_sessions[member.id] = time.time()
            return

        if not saiu or member.id not in self.voice_sessions:
            return

        inicio = self.voice_sessions.pop(member.id)
        minutos = int((time.time() - inicio) / 60)
        if minutos <= 0:
            return

        # Garante que o usuário existe antes do UPDATE
        await self.get_user_data(member.id, member.name)

        async with get_conexao() as db:
            async with db.execute(
                "SELECT voice_minutes, xp, level FROM usuarios WHERE id = ?",
                (member.id,),
            ) as cursor:
                row = await cursor.fetchone()

            if not row:
                return

            novo_voice = row["voice_minutes"] + minutos
            novo_xp = row["xp"] + (minutos * self.config.xp_per_voice_minute)
            level = row["level"]

            while novo_xp >= level * self.config.level_up_multiplier:
                novo_xp -= level * self.config.level_up_multiplier
                level += 1

            await db.execute(
                "UPDATE usuarios SET voice_minutes = ?, xp = ?, level = ? WHERE id = ?",
                (novo_voice, novo_xp, level, member.id),
            )
            await db.commit()

        if novo_voice >= MINUTOS_PARA_PODCASTER:
            await self.add_badge(member.id, BADGE_PODCASTER)

    # --- COMMANDS ---

    @app_commands.command(name="perfil", description="Ver Card de Jogador")
    @app_commands.describe(usuario="Usuário a consultar (padrão: você)")
    async def perfil(
        self,
        interaction: discord.Interaction,
        usuario: Optional[discord.Member] = None,
    ):
        """Mostra o card de perfil com XP, nível, streak e conquistas."""
        alvo = usuario or interaction.user
        user, badges = await self.get_user_data(alvo.id, alvo.name)

        embed = discord.Embed(color=0xFFD700)
        embed.set_author(
            name=f"Perfil de {alvo.display_name}", icon_url=alvo.display_avatar.url
        )
        embed.set_thumbnail(url=alvo.display_avatar.url)

        embed.add_field(name="📜 Bio", value=f"_{user['bio']}_", inline=False)
        embed.add_field(name="🔥 Streak", value=f"**{user['streak']}** dias", inline=True)
        embed.add_field(name="⭐ Nível", value=f"**{user['level']}**", inline=True)
        embed.add_field(
            name="🎙️ Voz", value=f"**{user['voice_minutes']}** min", inline=True
        )

        badges_display = " ".join(f"`{b}`" for b in badges) if badges else "Sem medalhas."
        embed.add_field(name="🏆 Conquistas", value=badges_display, inline=False)

        # Barra de progresso limitada a 10 blocos (antes estourava no level up)
        proximo = max(user["level"] * self.config.level_up_multiplier, 1)
        preenchido = min(max(int((user["xp"] / proximo) * 10), 0), 10)
        barra = "🟦" * preenchido + "⬛" * (10 - preenchido)
        embed.add_field(name=f"XP ({user['xp']}/{proximo})", value=barra, inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="bio", description="Muda a bio do perfil")
    @app_commands.describe(texto="Sua nova bio (máx. 100 caracteres)")
    async def bio(self, interaction: discord.Interaction, texto: str):
        """Atualiza a bio do usuário."""
        texto = texto.strip()
        if not texto:
            return await interaction.response.send_message(
                "❌ A bio não pode ficar vazia.", ephemeral=True
            )
        if len(texto) > 100:
            return await interaction.response.send_message(
                "❌ Máximo 100 caracteres.", ephemeral=True
            )

        # Garante que o registro existe antes de atualizar
        await self.get_user_data(interaction.user.id, interaction.user.name)

        async with get_conexao() as db:
            await db.execute(
                "UPDATE usuarios SET bio = ? WHERE id = ?",
                (texto, interaction.user.id),
            )
            await db.commit()

        await interaction.response.send_message("✅ Bio atualizada!", ephemeral=True)

    @app_commands.command(name="ranking", description="Top 10 do servidor")
    async def ranking(self, interaction: discord.Interaction):
        """Mostra o ranking de XP do servidor."""
        async with get_conexao() as db:
            async with db.execute(
                "SELECT nome, level, xp FROM usuarios ORDER BY level DESC, xp DESC LIMIT 10"
            ) as cursor:
                linhas = await cursor.fetchall()

        if not linhas:
            return await interaction.response.send_message(
                "❌ Ninguém pontuou ainda.", ephemeral=True
            )

        medalhas = ["🥇", "🥈", "🥉"]
        descricao = "\n".join(
            f"{medalhas[i] if i < len(medalhas) else f'`{i + 1}.`'} "
            f"**{linha['nome']}** — Nível {linha['level']} ({linha['xp']} XP)"
            for i, linha in enumerate(linhas)
        )

        embed = discord.Embed(
            title="🏆 Ranking do Servidor",
            description=descricao,
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="noticias", description="Jornal do Servidor (IA)")
    async def noticias(self, interaction: discord.Interaction):
        """Gera uma 'fofoca' do servidor com base no líder do ranking."""
        if not gemini.is_enabled:
            return await interaction.response.send_message(
                "❌ IA não configurada (defina GEMINI_API_KEY).", ephemeral=True
            )

        await interaction.response.defer()

        async with get_conexao() as db:
            async with db.execute(
                "SELECT nome, level FROM usuarios ORDER BY level DESC, xp DESC LIMIT 1"
            ) as cursor:
                top = await cursor.fetchone()

        if not top:
            return await interaction.followup.send("❌ Sem dados suficientes.")

        prompt = (
            "Escreva uma fofoca de jornal engraçada e leve, em português. "
            f"Destaque: {top['nome']} é o líder do servidor (Nível {top['level']}). "
            "Invente um boato inofensivo."
        )

        texto = await gemini.gerar(prompt)
        if not texto:
            return await interaction.followup.send("❌ IA indisponível no momento.")

        embed = discord.Embed(
            title="📰 CLUTCH NEWS",
            description=texto,
            color=discord.Color.orange(),
        )
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Social(bot))

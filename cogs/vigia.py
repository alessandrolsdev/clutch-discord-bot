"""
COG: VIGIA (LOGS DE MODERAÇÃO)
==============================

Registra mensagens apagadas e editadas em um **canal de logs configurável**.

Mudança importante de privacidade:
Antes, o conteúdo de toda mensagem apagada era republicado no mesmo canal
público onde ela havia sido apagada — ou seja, apagar uma mensagem fazia o bot
reexibi-la para todo mundo, inclusive dados que a pessoa quis remover. Agora
nada é publicado enquanto um admin não definir um canal de logs com
``/setlog``, e o log vai só para esse canal.
"""

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.guild_config import guild_config
from utils.logger import get_logger

logger = get_logger(__name__)

# Limite de caracteres exibidos por mensagem no log
MAX_CONTEUDO = 1000

# Nunca faz ping a partir de conteúdo logado
SEM_MENCOES = discord.AllowedMentions.none()


class Vigia(commands.Cog):
    """Cog de logs de moderação."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _canal_de_log(
        self, guild: Optional[discord.Guild]
    ) -> Optional[discord.abc.Messageable]:
        """
        Retorna o canal de logs configurado do servidor.

        Returns:
            Canal de texto, ou None se não configurado/inacessível
        """
        if guild is None:
            return None

        # Cache em memória: on_message_delete não pode fazer query por evento
        config = await guild_config.obter(guild.id)
        if not config.log_channel_id:
            return None

        canal = guild.get_channel(config.log_channel_id)
        if canal is None:
            logger.warning(
                "Canal de log %s não existe mais no servidor %s",
                config.log_channel_id,
                guild.id,
            )
            return None

        return canal

    @staticmethod
    def _truncar(conteudo: Optional[str]) -> str:
        """Formata o conteúdo de uma mensagem para exibição no log."""
        if not conteudo:
            return "_(sem texto — anexo, embed ou conteúdo não cacheado)_"
        if len(conteudo) > MAX_CONTEUDO:
            conteudo = conteudo[:MAX_CONTEUDO] + "…"
        return conteudo

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Registra mensagens apagadas no canal de logs."""
        if message.author.bot or not message.guild:
            return

        canal_log = await self._canal_de_log(message.guild)
        if canal_log is None:
            return

        embed = discord.Embed(
            title="🗑️ Mensagem apagada",
            description=self._truncar(message.content),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(
            name=f"{message.author} ({message.author.id})",
            icon_url=message.author.display_avatar.url,
        )
        embed.add_field(name="Canal", value=message.channel.mention, inline=True)

        try:
            await canal_log.send(embed=embed, allowed_mentions=SEM_MENCOES)
        except discord.HTTPException as e:
            logger.warning("Não foi possível enviar log de exclusão: %s", e)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Registra edições de mensagens no canal de logs."""
        if before.author.bot or not before.guild:
            return

        # Só avisa se o texto mudou mesmo (embeds carregando também disparam edit)
        if before.content == after.content:
            return

        canal_log = await self._canal_de_log(before.guild)
        if canal_log is None:
            return

        embed = discord.Embed(
            title="✏️ Mensagem editada",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(
            name=f"{before.author} ({before.author.id})",
            icon_url=before.author.display_avatar.url,
        )
        embed.add_field(name="Antes", value=self._truncar(before.content), inline=False)
        embed.add_field(name="Depois", value=self._truncar(after.content), inline=False)
        embed.add_field(
            name="Ir para a mensagem", value=after.jump_url, inline=False
        )

        try:
            await canal_log.send(embed=embed, allowed_mentions=SEM_MENCOES)
        except discord.HTTPException as e:
            logger.warning("Não foi possível enviar log de edição: %s", e)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Registra entradas de membros no canal de logs."""
        canal_log = await self._canal_de_log(member.guild)
        if canal_log is None:
            return

        embed = discord.Embed(
            title="📥 Membro entrou",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(
            name=f"{member} ({member.id})", icon_url=member.display_avatar.url
        )
        embed.add_field(
            name="Conta criada",
            value=discord.utils.format_dt(member.created_at, "R"),
            inline=True,
        )
        embed.add_field(
            name="Total de membros", value=str(member.guild.member_count), inline=True
        )

        try:
            await canal_log.send(embed=embed, allowed_mentions=SEM_MENCOES)
        except discord.HTTPException as e:
            logger.warning("Não foi possível registrar entrada: %s", e)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Registra saídas de membros no canal de logs."""
        canal_log = await self._canal_de_log(member.guild)
        if canal_log is None:
            return

        cargos = [r.mention for r in member.roles if not r.is_default()]

        embed = discord.Embed(
            title="📤 Membro saiu",
            color=discord.Color.dark_grey(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(
            name=f"{member} ({member.id})", icon_url=member.display_avatar.url
        )
        if member.joined_at:
            embed.add_field(
                name="Entrou em",
                value=discord.utils.format_dt(member.joined_at, "R"),
                inline=True,
            )
        embed.add_field(
            name="Cargos",
            value=", ".join(cargos)[:1024] if cargos else "_nenhum_",
            inline=False,
        )

        try:
            await canal_log.send(embed=embed, allowed_mentions=SEM_MENCOES)
        except discord.HTTPException as e:
            logger.warning("Não foi possível registrar saída: %s", e)

    @app_commands.command(
        name="setlog", description="Define o canal de logs de moderação"
    )
    @app_commands.describe(canal="Canal de logs (deixe vazio para desativar)")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def setlog(
        self,
        interaction: discord.Interaction,
        canal: Optional[discord.TextChannel] = None,
    ):
        """Configura (ou desativa) o canal de logs de moderação."""
        if canal is None:
            await guild_config.atualizar(interaction.guild.id, log_channel_id=None)
            return await interaction.response.send_message(
                "🔕 Logs de moderação desativados.", ephemeral=True
            )

        permissoes = canal.permissions_for(interaction.guild.me)
        if not (permissoes.send_messages and permissoes.embed_links):
            return await interaction.response.send_message(
                f"❌ Não tenho permissão de enviar embeds em {canal.mention}.",
                ephemeral=True,
            )

        await guild_config.atualizar(interaction.guild.id, log_channel_id=canal.id)
        await interaction.response.send_message(
            f"✅ Logs de moderação vão para {canal.mention}.", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Vigia(bot))

"""
COG: PORTEIRO (BOAS-VINDAS)
===========================

Envia um cartão de boas-vindas quando alguém entra no servidor.

Ordem de escolha do canal:
1. Canal de sistema do servidor
2. Canal chamado "geral" ou "chat"
Em ambos os casos, só envia se o bot realmente puder escrever lá.
"""

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.guild_config import guild_config
from utils.logger import get_logger

logger = get_logger(__name__)

NOMES_DE_CANAL_FALLBACK = ("geral", "chat", "bem-vindo", "boas-vindas")


class Porteiro(commands.Cog):
    """Cog de mensagens de boas-vindas."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def _pode_escrever(guild: discord.Guild, canal: Optional[discord.abc.GuildChannel]) -> bool:
        """True se o bot pode enviar embeds no canal."""
        if canal is None or not isinstance(canal, discord.TextChannel):
            return False
        permissoes = canal.permissions_for(guild.me)
        return permissoes.send_messages and permissoes.embed_links

    def _escolher_canal(
        self, guild: discord.Guild, canal_configurado: Optional[int] = None
    ) -> Optional[discord.TextChannel]:
        """
        Escolhe um canal onde o bot possa enviar as boas-vindas.

        Ordem: canal configurado em /boasvindas > canal de sistema > nomes comuns.

        Returns:
            Canal utilizável, ou None se não houver
        """

        def pode_escrever(canal) -> bool:
            return self._pode_escrever(guild, canal)

        # Preferência explícita do servidor
        if canal_configurado:
            canal = guild.get_channel(canal_configurado)
            if pode_escrever(canal):
                return canal
            logger.warning(
                "Canal de boas-vindas %s inacessível em %s", canal_configurado, guild.id
            )

        if pode_escrever(guild.system_channel):
            return guild.system_channel

        for nome in NOMES_DE_CANAL_FALLBACK:
            canal = discord.utils.get(guild.text_channels, name=nome)
            if pode_escrever(canal):
                return canal

        return None

    async def dar_boas_vindas(self, member: discord.Member) -> bool:
        """
        Envia o cartão de boas-vindas para um membro.

        Args:
            member: Membro que entrou

        Returns:
            True se a mensagem foi enviada
        """
        config = await guild_config.obter(member.guild.id)
        if not config.welcome_enabled:
            return False

        canal = self._escolher_canal(member.guild, config.welcome_channel_id)
        if canal is None:
            logger.info(
                "Nenhum canal disponível para boas-vindas em %s", member.guild.id
            )
            return False

        embed = discord.Embed(
            title=f"👋 Bem-vindo(a), {member.display_name}!",
            description=(
                f"Seja muito bem-vindo ao servidor **{member.guild.name}**!\n"
                "Não esqueça de ler as regras."
            ),
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        try:
            await canal.send(
                f"Olha quem chegou! {member.mention}",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    everyone=False, roles=False, users=[member]
                ),
            )
            return True
        except discord.HTTPException as e:
            logger.warning("Falha ao enviar boas-vindas: %s", e)
            return False

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Dispara as boas-vindas quando alguém entra no servidor."""
        await self.dar_boas_vindas(member)

    @app_commands.command(
        name="boasvindas", description="Configura o canal de boas-vindas"
    )
    @app_commands.describe(
        canal="Canal das boas-vindas (vazio = escolha automática)",
        ativo="Ligar ou desligar as boas-vindas",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def boasvindas(
        self,
        interaction: discord.Interaction,
        canal: Optional[discord.TextChannel] = None,
        ativo: bool = True,
    ):
        """Define canal e estado das mensagens de boas-vindas."""
        if canal and not self._pode_escrever(interaction.guild, canal):
            return await interaction.response.send_message(
                f"❌ Não tenho permissão de enviar embeds em {canal.mention}.",
                ephemeral=True,
            )

        await guild_config.atualizar(
            interaction.guild.id,
            welcome_channel_id=canal.id if canal else None,
            welcome_enabled=int(ativo),
        )

        if not ativo:
            return await interaction.response.send_message(
                "🔕 Boas-vindas desativadas.", ephemeral=True
            )

        destino = canal.mention if canal else "_escolha automática_"
        await interaction.response.send_message(
            f"✅ Boas-vindas ativadas em {destino}.", ephemeral=True
        )

    @commands.command(name="testar_boasvindas")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def testar_boasvindas(self, ctx: commands.Context):
        """Simula a entrada de alguém para testar o cartão (só administradores)."""
        enviado = await self.dar_boas_vindas(ctx.author)
        if not enviado:
            await ctx.send(
                "⚠️ Não encontrei um canal onde eu possa enviar as boas-vindas."
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Porteiro(bot))

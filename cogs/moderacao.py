"""
COG: MODERAÇÃO
==============

Ferramentas de moderação inspiradas em Dyno/Carl-bot.

Comandos: /ban /unban /kick /castigo /descastigo /limpar /avisar /avisos
          /removeraviso /limparavisos /lento /trancar /destrancar

Garantias aplicadas em todas as punições:
- **Hierarquia**: ninguém pune alguém de cargo igual ou superior ao seu, e o
  bot não tenta punir quem está acima dele (a API recusaria de qualquer forma).
- **Auto-proteção**: não dá para punir a si mesmo, o dono do servidor ou o bot.
- **Aviso por DM**: o punido recebe o motivo antes da ação (best-effort).
- **Auditoria**: toda ação vai para o canal de logs definido em ``/setlog``.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from infra.database import (
    adicionar_warn,
    limpar_warns,
    listar_warns,
    remover_warn,
)
from utils.guild_config import guild_config
from utils.logger import get_logger

logger = get_logger(__name__)

# Discord limita o timeout a 28 dias
MAX_DIAS_CASTIGO = 28

# Limite de mensagens por chamada de purge (limite prático da API de bulk delete)
MAX_LIMPAR = 100

SEM_MENCOES = discord.AllowedMentions.none()


class ErroDeHierarquia(Exception):
    """A ação viola a hierarquia de cargos ou uma proteção básica."""


class Moderacao(commands.Cog):
    """Cog de moderação."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- VALIDAÇÕES ---

    @staticmethod
    def validar_alvo(
        interaction: discord.Interaction, alvo: discord.Member, acao: str
    ) -> None:
        """
        Verifica se o moderador pode aplicar a ação no alvo.

        Args:
            interaction: Interação do moderador
            alvo: Membro a ser punido
            acao: Nome da ação (usado na mensagem de erro)

        Raises:
            ErroDeHierarquia: Se a ação não é permitida
        """
        autor = interaction.user
        guild = interaction.guild

        if alvo.id == autor.id:
            raise ErroDeHierarquia(f"Você não pode {acao} a si mesmo.")

        if alvo.id == guild.me.id:
            raise ErroDeHierarquia(f"Não vou {acao} a mim mesmo.")

        if alvo.id == guild.owner_id:
            raise ErroDeHierarquia(f"Não é possível {acao} o dono do servidor.")

        # O dono do servidor passa por cima da checagem de cargo
        if autor.id != guild.owner_id and alvo.top_role >= autor.top_role:
            raise ErroDeHierarquia(
                f"Você não pode {acao} alguém com cargo igual ou superior ao seu."
            )

        if alvo.top_role >= guild.me.top_role:
            raise ErroDeHierarquia(
                f"Meu cargo está abaixo do de {alvo.mention}; não consigo {acao}."
            )

    # --- AUDITORIA ---

    async def registrar_log(
        self,
        guild: discord.Guild,
        titulo: str,
        cor: discord.Color,
        alvo: discord.abc.User,
        moderador: discord.abc.User,
        motivo: Optional[str],
        extra: Optional[dict] = None,
    ) -> None:
        """
        Publica a ação no canal de logs configurado.

        Silencioso se o servidor não configurou ``/setlog``.
        """
        config = await guild_config.obter(guild.id)
        if not config.log_channel_id:
            return

        canal = guild.get_channel(config.log_channel_id)
        if canal is None:
            return

        embed = discord.Embed(
            title=titulo, color=cor, timestamp=datetime.now(timezone.utc)
        )
        embed.set_author(name=f"{alvo} ({alvo.id})", icon_url=alvo.display_avatar.url)
        embed.add_field(name="Moderador", value=moderador.mention, inline=True)
        embed.add_field(name="Motivo", value=motivo or "_Não informado_", inline=False)

        for nome, valor in (extra or {}).items():
            embed.add_field(name=nome, value=valor, inline=True)

        try:
            await canal.send(embed=embed, allowed_mentions=SEM_MENCOES)
        except discord.HTTPException as e:
            logger.warning("Falha ao registrar log de moderação: %s", e)

    @staticmethod
    async def avisar_por_dm(
        alvo: discord.Member, guild_name: str, acao: str, motivo: Optional[str]
    ) -> bool:
        """
        Avisa o usuário por DM sobre a punição.

        Returns:
            True se a DM foi entregue (usuários podem ter DMs fechadas)
        """
        embed = discord.Embed(
            title=f"Você recebeu: {acao}",
            description=f"Servidor: **{guild_name}**",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Motivo", value=motivo or "_Não informado_")

        try:
            await alvo.send(embed=embed)
            return True
        except discord.HTTPException:
            return False

    # --- COMANDOS DE PUNIÇÃO ---

    @app_commands.command(name="ban", description="Bane um membro do servidor")
    @app_commands.describe(
        membro="Quem será banido",
        motivo="Motivo do banimento",
        apagar_dias="Apagar mensagens dos últimos N dias (0-7)",
    )
    @app_commands.default_permissions(ban_members=True)
    @app_commands.guild_only()
    async def ban(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        motivo: Optional[str] = None,
        apagar_dias: app_commands.Range[int, 0, 7] = 0,
    ):
        """Bane um membro."""
        try:
            self.validar_alvo(interaction, membro, "banir")
        except ErroDeHierarquia as e:
            return await interaction.response.send_message(f"❌ {e}", ephemeral=True)

        await interaction.response.defer()

        # Avisa antes de banir — depois o bot perde acesso ao usuário
        dm_ok = await self.avisar_por_dm(
            membro, interaction.guild.name, "Banimento", motivo
        )

        try:
            await membro.ban(
                reason=f"{interaction.user}: {motivo or 'sem motivo'}",
                delete_message_days=apagar_dias,
            )
        except discord.Forbidden:
            return await interaction.followup.send("❌ Sem permissão para banir.")
        except discord.HTTPException as e:
            return await interaction.followup.send(f"❌ Falha ao banir: {e}")

        await interaction.followup.send(
            f"🔨 **{membro}** foi banido." + ("" if dm_ok else " (DM não entregue)")
        )
        await self.registrar_log(
            interaction.guild,
            "🔨 Membro banido",
            discord.Color.red(),
            membro,
            interaction.user,
            motivo,
        )

    @app_commands.command(name="unban", description="Remove o banimento de um usuário")
    @app_commands.describe(user_id="ID do usuário banido", motivo="Motivo do desbanimento")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.guild_only()
    async def unban(
        self,
        interaction: discord.Interaction,
        user_id: str,
        motivo: Optional[str] = None,
    ):
        """Remove o banimento de um usuário pelo ID."""
        if not user_id.strip().isdigit():
            return await interaction.response.send_message(
                "❌ Informe um ID numérico.", ephemeral=True
            )

        await interaction.response.defer()

        try:
            usuario = discord.Object(id=int(user_id))
            await interaction.guild.unban(
                usuario, reason=f"{interaction.user}: {motivo or 'sem motivo'}"
            )
        except discord.NotFound:
            return await interaction.followup.send("❌ Esse usuário não está banido.")
        except discord.Forbidden:
            return await interaction.followup.send("❌ Sem permissão para desbanir.")
        except discord.HTTPException as e:
            return await interaction.followup.send(f"❌ Falha ao desbanir: {e}")

        await interaction.followup.send(f"✅ Banimento de `{user_id}` removido.")

    @app_commands.command(name="kick", description="Expulsa um membro do servidor")
    @app_commands.describe(membro="Quem será expulso", motivo="Motivo da expulsão")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.guild_only()
    async def kick(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        motivo: Optional[str] = None,
    ):
        """Expulsa um membro."""
        try:
            self.validar_alvo(interaction, membro, "expulsar")
        except ErroDeHierarquia as e:
            return await interaction.response.send_message(f"❌ {e}", ephemeral=True)

        await interaction.response.defer()

        dm_ok = await self.avisar_por_dm(
            membro, interaction.guild.name, "Expulsão", motivo
        )

        try:
            await membro.kick(reason=f"{interaction.user}: {motivo or 'sem motivo'}")
        except discord.Forbidden:
            return await interaction.followup.send("❌ Sem permissão para expulsar.")
        except discord.HTTPException as e:
            return await interaction.followup.send(f"❌ Falha ao expulsar: {e}")

        await interaction.followup.send(
            f"👢 **{membro}** foi expulso." + ("" if dm_ok else " (DM não entregue)")
        )
        await self.registrar_log(
            interaction.guild,
            "👢 Membro expulso",
            discord.Color.orange(),
            membro,
            interaction.user,
            motivo,
        )

    @app_commands.command(name="castigo", description="Silencia um membro temporariamente")
    @app_commands.describe(
        membro="Quem será silenciado",
        minutos="Duração em minutos (máx. 40320 = 28 dias)",
        motivo="Motivo do castigo",
    )
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def castigo(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        minutos: app_commands.Range[int, 1, MAX_DIAS_CASTIGO * 24 * 60],
        motivo: Optional[str] = None,
    ):
        """Aplica timeout (castigo) em um membro."""
        try:
            self.validar_alvo(interaction, membro, "castigar")
        except ErroDeHierarquia as e:
            return await interaction.response.send_message(f"❌ {e}", ephemeral=True)

        await interaction.response.defer()

        duracao = timedelta(minutes=minutos)

        try:
            await membro.timeout(
                duracao, reason=f"{interaction.user}: {motivo or 'sem motivo'}"
            )
        except discord.Forbidden:
            return await interaction.followup.send("❌ Sem permissão para castigar.")
        except discord.HTTPException as e:
            return await interaction.followup.send(f"❌ Falha ao castigar: {e}")

        fim = discord.utils.utcnow() + duracao
        await self.avisar_por_dm(
            membro,
            interaction.guild.name,
            f"Castigo de {minutos} min",
            motivo,
        )

        await interaction.followup.send(
            f"🔇 **{membro}** silenciado até {discord.utils.format_dt(fim, 'R')}."
        )
        await self.registrar_log(
            interaction.guild,
            "🔇 Membro castigado",
            discord.Color.dark_orange(),
            membro,
            interaction.user,
            motivo,
            {"Duração": f"{minutos} min", "Termina": discord.utils.format_dt(fim, "f")},
        )

    @app_commands.command(name="descastigo", description="Remove o castigo de um membro")
    @app_commands.describe(membro="Quem será liberado")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def descastigo(
        self, interaction: discord.Interaction, membro: discord.Member
    ):
        """Remove o timeout de um membro."""
        if not membro.is_timed_out():
            return await interaction.response.send_message(
                "❌ Esse membro não está de castigo.", ephemeral=True
            )

        await interaction.response.defer()

        try:
            await membro.timeout(None, reason=f"Liberado por {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send("❌ Sem permissão.")
        except discord.HTTPException as e:
            return await interaction.followup.send(f"❌ Falha: {e}")

        await interaction.followup.send(f"🔊 **{membro}** foi liberado.")
        await self.registrar_log(
            interaction.guild,
            "🔊 Castigo removido",
            discord.Color.green(),
            membro,
            interaction.user,
            None,
        )

    @app_commands.command(name="limpar", description="Apaga mensagens do canal")
    @app_commands.describe(
        quantidade="Quantas mensagens apagar (1-100)",
        membro="Apagar apenas mensagens deste membro",
    )
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def limpar(
        self,
        interaction: discord.Interaction,
        quantidade: app_commands.Range[int, 1, MAX_LIMPAR],
        membro: Optional[discord.Member] = None,
    ):
        """Apaga mensagens em massa, opcionalmente filtrando por autor."""
        await interaction.response.defer(ephemeral=True)

        def filtro(mensagem: discord.Message) -> bool:
            return membro is None or mensagem.author.id == membro.id

        try:
            apagadas = await interaction.channel.purge(
                limit=quantidade if membro is None else quantidade * 5,
                check=filtro,
                # A API não faz bulk delete de mensagens com mais de 14 dias
                after=discord.utils.utcnow() - timedelta(days=14),
            )
        except discord.Forbidden:
            return await interaction.followup.send(
                "❌ Sem permissão para apagar mensagens.", ephemeral=True
            )
        except discord.HTTPException as e:
            return await interaction.followup.send(f"❌ Falha: {e}", ephemeral=True)

        total = len(apagadas[:quantidade]) if membro else len(apagadas)

        await interaction.followup.send(
            f"🧹 Apaguei **{total}** mensagens"
            + (f" de **{membro}**." if membro else "."),
            ephemeral=True,
        )
        await self.registrar_log(
            interaction.guild,
            "🧹 Mensagens apagadas",
            discord.Color.greyple(),
            membro or interaction.user,
            interaction.user,
            f"{total} mensagens em {interaction.channel.mention}",
        )

    # --- ADVERTÊNCIAS ---

    @app_commands.command(name="avisar", description="Adverte um membro")
    @app_commands.describe(membro="Quem será advertido", motivo="Motivo da advertência")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def avisar(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        motivo: Optional[str] = None,
    ):
        """Registra uma advertência no histórico do membro."""
        try:
            self.validar_alvo(interaction, membro, "advertir")
        except ErroDeHierarquia as e:
            return await interaction.response.send_message(f"❌ {e}", ephemeral=True)

        await interaction.response.defer()

        total = await adicionar_warn(
            interaction.guild.id, membro.id, interaction.user.id, motivo
        )

        await self.avisar_por_dm(
            membro, interaction.guild.name, f"Advertência (total: {total})", motivo
        )

        await interaction.followup.send(
            f"⚠️ **{membro}** advertido. Total de avisos: **{total}**."
        )
        await self.registrar_log(
            interaction.guild,
            "⚠️ Advertência aplicada",
            discord.Color.yellow(),
            membro,
            interaction.user,
            motivo,
            {"Total de avisos": str(total)},
        )

    @app_commands.command(name="avisos", description="Lista as advertências de um membro")
    @app_commands.describe(membro="De quem? (padrão: você)")
    @app_commands.guild_only()
    async def avisos(
        self,
        interaction: discord.Interaction,
        membro: Optional[discord.Member] = None,
    ):
        """Mostra o histórico de advertências."""
        alvo = membro or interaction.user

        # Ver avisos dos outros exige permissão de moderação
        if alvo.id != interaction.user.id:
            permissoes = interaction.user.guild_permissions
            if not (permissoes.moderate_members or permissoes.administrator):
                return await interaction.response.send_message(
                    "❌ Você só pode ver os seus próprios avisos.", ephemeral=True
                )

        registros = await listar_warns(interaction.guild.id, alvo.id)

        if not registros:
            return await interaction.response.send_message(
                f"✅ **{alvo.display_name}** não tem advertências.", ephemeral=True
            )

        embed = discord.Embed(
            title=f"⚠️ Advertências de {alvo.display_name}",
            description=f"Total: **{len(registros)}**",
            color=discord.Color.yellow(),
        )

        # Embeds aceitam no máximo 25 fields
        for registro in registros[:25]:
            try:
                quando = datetime.fromisoformat(registro["created_at"])
                data = discord.utils.format_dt(quando, "R")
            except ValueError:
                data = registro["created_at"]

            embed.add_field(
                name=f"#{registro['id']} • {data}",
                value=(
                    f"**Motivo:** {registro['reason'] or '_não informado_'}\n"
                    f"**Moderador:** <@{registro['moderator_id']}>"
                ),
                inline=False,
            )

        if len(registros) > 25:
            embed.set_footer(text=f"Mostrando 25 de {len(registros)} advertências")

        await interaction.response.send_message(
            embed=embed, ephemeral=True, allowed_mentions=SEM_MENCOES
        )

    @app_commands.command(name="removeraviso", description="Remove uma advertência pelo ID")
    @app_commands.describe(aviso_id="ID do aviso (veja em /avisos)")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def removeraviso(self, interaction: discord.Interaction, aviso_id: int):
        """Apaga uma advertência específica."""
        removido = await remover_warn(interaction.guild.id, aviso_id)

        if not removido:
            return await interaction.response.send_message(
                f"❌ Aviso `#{aviso_id}` não encontrado.", ephemeral=True
            )

        await interaction.response.send_message(f"✅ Aviso `#{aviso_id}` removido.")

    @app_commands.command(
        name="limparavisos", description="Remove todas as advertências de um membro"
    )
    @app_commands.describe(membro="De quem?")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def limparavisos(
        self, interaction: discord.Interaction, membro: discord.Member
    ):
        """Zera o histórico de advertências de um membro."""
        total = await limpar_warns(interaction.guild.id, membro.id)

        if not total:
            return await interaction.response.send_message(
                f"ℹ️ **{membro.display_name}** já não tinha avisos.", ephemeral=True
            )

        await interaction.response.send_message(
            f"🧹 Removi **{total}** avisos de **{membro.display_name}**."
        )
        await self.registrar_log(
            interaction.guild,
            "🧹 Avisos limpos",
            discord.Color.green(),
            membro,
            interaction.user,
            f"{total} advertências removidas",
        )

    # --- CANAL ---

    @app_commands.command(name="lento", description="Define o modo lento do canal")
    @app_commands.describe(segundos="Intervalo entre mensagens (0 desliga, máx. 21600)")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def lento(
        self,
        interaction: discord.Interaction,
        segundos: app_commands.Range[int, 0, 21600],
    ):
        """Ajusta o slowmode do canal atual."""
        try:
            await interaction.channel.edit(
                slowmode_delay=segundos, reason=f"Ajustado por {interaction.user}"
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ Sem permissão para editar o canal.", ephemeral=True
            )
        except discord.HTTPException as e:
            return await interaction.response.send_message(f"❌ Falha: {e}", ephemeral=True)

        if segundos == 0:
            await interaction.response.send_message("🚀 Modo lento desligado.")
        else:
            await interaction.response.send_message(
                f"🐌 Modo lento: **{segundos}s** entre mensagens."
            )

    @app_commands.command(name="trancar", description="Impede novas mensagens no canal")
    @app_commands.describe(motivo="Motivo do trancamento")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def trancar(
        self, interaction: discord.Interaction, motivo: Optional[str] = None
    ):
        """Tranca o canal para o cargo @everyone."""
        canal = interaction.channel
        permissoes = canal.overwrites_for(interaction.guild.default_role)

        if permissoes.send_messages is False:
            return await interaction.response.send_message(
                "ℹ️ Este canal já está trancado.", ephemeral=True
            )

        permissoes.send_messages = False

        try:
            await canal.set_permissions(
                interaction.guild.default_role,
                overwrite=permissoes,
                reason=f"{interaction.user}: {motivo or 'sem motivo'}",
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ Sem permissão para editar o canal.", ephemeral=True
            )

        embed = discord.Embed(
            title="🔒 Canal trancado",
            description=motivo or "_Sem motivo informado_",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="destrancar", description="Libera as mensagens no canal")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def destrancar(self, interaction: discord.Interaction):
        """Destranca o canal para o cargo @everyone."""
        canal = interaction.channel
        permissoes = canal.overwrites_for(interaction.guild.default_role)

        if permissoes.send_messages is not False:
            return await interaction.response.send_message(
                "ℹ️ Este canal não está trancado.", ephemeral=True
            )

        # None devolve a permissão ao padrão da categoria/servidor
        permissoes.send_messages = None

        try:
            await canal.set_permissions(
                interaction.guild.default_role,
                overwrite=permissoes,
                reason=f"Destrancado por {interaction.user}",
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ Sem permissão para editar o canal.", ephemeral=True
            )

        await interaction.response.send_message("🔓 Canal destrancado.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderacao(bot))

"""
COG: CARGOS
===========

Automação de cargos, no estilo MEE6 (recompensas por nível) e Carl-bot
(painéis de auto-atribuição).

Recursos:
- **Cargos por nível**: sobe de nível, ganha o cargo automaticamente.
- **Autorole**: cargo concedido a quem entra no servidor.
- **Painéis de cargo**: botões que o membro clica para pegar/largar um cargo.

Os painéis usam **views persistentes**: os botões continuam funcionando depois
de reiniciar o bot, porque cada um carrega um ``custom_id`` estável e o painel
é registrado de novo no startup a partir do banco.
"""

from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from infra.database import (
    definir_level_role,
    listar_level_roles,
    listar_paineis_cargos,
    remover_level_role,
    remover_painel_cargos,
    salvar_painel_cargos,
)
from utils.guild_config import guild_config
from utils.logger import get_logger

logger = get_logger(__name__)

# Prefixo do custom_id dos botões de cargo. O ID do cargo vem depois.
CUSTOM_ID_PREFIX = "clutch:rolebtn:"

# Discord permite 5 botões por linha e 5 linhas; limitamos a 1 linha
MAX_CARGOS_POR_PAINEL = 5


class BotaoCargo(discord.ui.Button):
    """Botão que concede ou remove um cargo de quem clica."""

    def __init__(self, role_id: int, label: str, emoji: Optional[str] = None):
        super().__init__(
            label=label,
            emoji=emoji or None,
            style=discord.ButtonStyle.secondary,
            # custom_id estável = o botão sobrevive ao restart do bot
            custom_id=f"{CUSTOM_ID_PREFIX}{role_id}",
        )
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        """Alterna o cargo do usuário."""
        guild = interaction.guild
        if guild is None:
            return

        cargo = guild.get_role(self.role_id)
        if cargo is None:
            return await interaction.response.send_message(
                "❌ Esse cargo não existe mais.", ephemeral=True
            )

        if cargo >= guild.me.top_role:
            return await interaction.response.send_message(
                "❌ Meu cargo está abaixo desse; não consigo atribuí-lo.",
                ephemeral=True,
            )

        try:
            if cargo in interaction.user.roles:
                await interaction.user.remove_roles(cargo, reason="Painel de cargos")
                await interaction.response.send_message(
                    f"➖ Removi o cargo **{cargo.name}**.", ephemeral=True
                )
            else:
                await interaction.user.add_roles(cargo, reason="Painel de cargos")
                await interaction.response.send_message(
                    f"➕ Você recebeu o cargo **{cargo.name}**.", ephemeral=True
                )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Não tenho permissão para gerenciar esse cargo.", ephemeral=True
            )
        except discord.HTTPException as e:
            logger.warning("Falha ao alternar cargo %s: %s", self.role_id, e)
            await interaction.response.send_message(f"❌ Falha: {e}", ephemeral=True)


class PainelCargosView(discord.ui.View):
    """View persistente com os botões de cargo de um painel."""

    def __init__(self, itens: List[dict]):
        # timeout=None é obrigatório para views persistentes
        super().__init__(timeout=None)
        for item in itens:
            self.add_item(
                BotaoCargo(item["role_id"], item["label"], item.get("emoji"))
            )


class Cargos(commands.Cog):
    """Cog de automação de cargos."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        """Registra as views persistentes dos painéis já criados."""
        try:
            paineis = await listar_paineis_cargos()
        except Exception as e:
            logger.error("Não foi possível carregar painéis de cargo: %s", e)
            return

        for painel in paineis:
            if not painel["itens"]:
                continue
            self.bot.add_view(
                PainelCargosView(painel["itens"]), message_id=painel["message_id"]
            )

        if paineis:
            logger.info("♻️  %s painéis de cargo restaurados", len(paineis))

    # --- API USADA POR OUTROS COGS ---

    async def conceder_cargos_de_nivel(
        self, member: discord.Member, level: int
    ) -> List[discord.Role]:
        """
        Concede os cargos de nível que o membro já alcançou.

        Chamado pelo cog Social no level up. Concede todos os cargos de nível
        menor ou igual ao atual, para o caso de o membro ter pulado níveis ou
        de a recompensa ter sido criada depois.

        Args:
            member: Membro que subiu de nível
            level: Nível atingido

        Returns:
            Cargos efetivamente concedidos agora
        """
        recompensas = await listar_level_roles(member.guild.id)
        if not recompensas:
            return []

        guild = member.guild
        atuais = {r.id for r in member.roles}
        a_conceder = []

        for recompensa in recompensas:
            if recompensa["level"] > level:
                break  # a lista vem ordenada por nível

            cargo = guild.get_role(recompensa["role_id"])
            if cargo is None or cargo.id in atuais:
                continue
            if cargo >= guild.me.top_role:
                logger.warning(
                    "Cargo %s está acima do bot em %s; ignorado", cargo.id, guild.id
                )
                continue

            a_conceder.append(cargo)

        if not a_conceder:
            return []

        try:
            await member.add_roles(*a_conceder, reason=f"Recompensa do nível {level}")
        except discord.Forbidden:
            logger.warning("Sem permissão para dar cargos de nível em %s", guild.id)
            return []
        except discord.HTTPException as e:
            logger.warning("Falha ao dar cargos de nível: %s", e)
            return []

        return a_conceder

    # --- AUTOROLE ---

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Concede o autorole configurado a quem entra."""
        if member.bot:
            return

        config = await guild_config.obter(member.guild.id)
        if not config.autorole_id:
            return

        cargo = member.guild.get_role(config.autorole_id)
        if cargo is None:
            logger.warning(
                "Autorole %s não existe mais em %s", config.autorole_id, member.guild.id
            )
            return

        if cargo >= member.guild.me.top_role:
            logger.warning("Autorole %s está acima do bot; ignorado", cargo.id)
            return

        try:
            await member.add_roles(cargo, reason="Autorole")
        except discord.HTTPException as e:
            logger.warning("Falha ao aplicar autorole: %s", e)

    # --- COMANDOS: CARGOS POR NÍVEL ---

    nivelcargo = app_commands.Group(
        name="nivelcargo",
        description="Cargos concedidos automaticamente por nível",
        default_permissions=discord.Permissions(manage_roles=True),
        guild_only=True,
    )

    @nivelcargo.command(name="definir", description="Define o cargo de um nível")
    @app_commands.describe(nivel="Nível necessário", cargo="Cargo a conceder")
    async def nivelcargo_definir(
        self,
        interaction: discord.Interaction,
        nivel: app_commands.Range[int, 1, 1000],
        cargo: discord.Role,
    ):
        """Associa um cargo a um nível."""
        if cargo >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                f"❌ **{cargo.name}** está acima do meu cargo — eu não conseguiria "
                "concedê-lo. Mova meu cargo para cima na lista.",
                ephemeral=True,
            )

        if cargo.is_default() or cargo.managed:
            return await interaction.response.send_message(
                "❌ Esse cargo não pode ser atribuído manualmente.", ephemeral=True
            )

        await definir_level_role(interaction.guild.id, nivel, cargo.id)
        await interaction.response.send_message(
            f"✅ Quem chegar ao **nível {nivel}** vai receber {cargo.mention}.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @nivelcargo.command(name="remover", description="Remove a recompensa de um nível")
    @app_commands.describe(nivel="Nível a limpar")
    async def nivelcargo_remover(
        self, interaction: discord.Interaction, nivel: app_commands.Range[int, 1, 1000]
    ):
        """Remove a recompensa de um nível."""
        removido = await remover_level_role(interaction.guild.id, nivel)

        if not removido:
            return await interaction.response.send_message(
                f"❌ O nível {nivel} não tinha recompensa.", ephemeral=True
            )

        await interaction.response.send_message(
            f"✅ Recompensa do nível {nivel} removida."
        )

    @nivelcargo.command(name="listar", description="Lista os cargos por nível")
    async def nivelcargo_listar(self, interaction: discord.Interaction):
        """Mostra todas as recompensas configuradas."""
        recompensas = await listar_level_roles(interaction.guild.id)

        if not recompensas:
            return await interaction.response.send_message(
                "ℹ️ Nenhum cargo por nível configurado. Use `/nivelcargo definir`.",
                ephemeral=True,
            )

        linhas = []
        for recompensa in recompensas:
            cargo = interaction.guild.get_role(recompensa["role_id"])
            nome = cargo.mention if cargo else f"`cargo apagado ({recompensa['role_id']})`"
            linhas.append(f"**Nível {recompensa['level']}** → {nome}")

        embed = discord.Embed(
            title="🎖️ Cargos por Nível",
            description="\n".join(linhas),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(
            embed=embed, allowed_mentions=discord.AllowedMentions.none()
        )

    # --- COMANDOS: AUTOROLE ---

    @app_commands.command(
        name="autorole", description="Cargo dado automaticamente a quem entra"
    )
    @app_commands.describe(cargo="Deixe vazio para desativar")
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def autorole(
        self, interaction: discord.Interaction, cargo: Optional[discord.Role] = None
    ):
        """Define ou desativa o autorole do servidor."""
        if cargo is None:
            await guild_config.atualizar(interaction.guild.id, autorole_id=None)
            return await interaction.response.send_message(
                "🔕 Autorole desativado.", ephemeral=True
            )

        if cargo >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                f"❌ **{cargo.name}** está acima do meu cargo.", ephemeral=True
            )

        if cargo.is_default() or cargo.managed:
            return await interaction.response.send_message(
                "❌ Esse cargo não pode ser atribuído manualmente.", ephemeral=True
            )

        await guild_config.atualizar(interaction.guild.id, autorole_id=cargo.id)
        await interaction.response.send_message(
            f"✅ Novos membros vão receber {cargo.mention}.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    # --- COMANDOS: PAINEL DE CARGOS ---

    @app_commands.command(
        name="painelcargos", description="Cria um painel de cargos com botões"
    )
    @app_commands.describe(
        titulo="Título do painel",
        descricao="Texto explicativo",
        cargo1="Cargo do 1º botão",
        cargo2="Cargo do 2º botão",
        cargo3="Cargo do 3º botão",
        cargo4="Cargo do 4º botão",
        cargo5="Cargo do 5º botão",
    )
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def painelcargos(
        self,
        interaction: discord.Interaction,
        titulo: str,
        cargo1: discord.Role,
        descricao: Optional[str] = None,
        cargo2: Optional[discord.Role] = None,
        cargo3: Optional[discord.Role] = None,
        cargo4: Optional[discord.Role] = None,
        cargo5: Optional[discord.Role] = None,
    ):
        """Publica um painel onde os membros pegam cargos clicando em botões."""
        cargos = [c for c in (cargo1, cargo2, cargo3, cargo4, cargo5) if c is not None]

        # Cargos repetidos gerariam custom_id duplicado na mesma view
        vistos = set()
        unicos = []
        for cargo in cargos:
            if cargo.id not in vistos:
                vistos.add(cargo.id)
                unicos.append(cargo)
        cargos = unicos[:MAX_CARGOS_POR_PAINEL]

        acima = [c.name for c in cargos if c >= interaction.guild.me.top_role]
        if acima:
            return await interaction.response.send_message(
                f"❌ Estes cargos estão acima do meu: {', '.join(acima)}.",
                ephemeral=True,
            )

        invalidos = [c.name for c in cargos if c.is_default() or c.managed]
        if invalidos:
            return await interaction.response.send_message(
                f"❌ Estes cargos não podem ser atribuídos: {', '.join(invalidos)}.",
                ephemeral=True,
            )

        itens = [{"role_id": c.id, "label": c.name[:80], "emoji": None} for c in cargos]

        embed = discord.Embed(
            title=titulo[:256],
            description=descricao or "Clique nos botões para pegar ou largar um cargo.",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Clique de novo para remover o cargo")

        await interaction.response.send_message(
            embed=embed, view=PainelCargosView(itens)
        )
        mensagem = await interaction.original_response()

        await salvar_painel_cargos(
            mensagem.id, interaction.guild.id, interaction.channel.id, itens
        )
        logger.info("Painel de cargos %s criado em %s", mensagem.id, interaction.guild.id)

    @app_commands.command(
        name="removerpainel", description="Desativa um painel de cargos"
    )
    @app_commands.describe(mensagem_id="ID da mensagem do painel")
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def removerpainel(self, interaction: discord.Interaction, mensagem_id: str):
        """Remove um painel de cargos do banco (os botões param de responder)."""
        if not mensagem_id.strip().isdigit():
            return await interaction.response.send_message(
                "❌ Informe um ID numérico de mensagem.", ephemeral=True
            )

        removido = await remover_painel_cargos(int(mensagem_id))

        if not removido:
            return await interaction.response.send_message(
                "❌ Painel não encontrado.", ephemeral=True
            )

        await interaction.response.send_message(
            "✅ Painel removido. Reinicie o bot para desativar os botões antigos.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Cargos(bot))

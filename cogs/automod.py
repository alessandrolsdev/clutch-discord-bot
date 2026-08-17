"""
COG: AUTOMOD
============

Moderação automática de mensagens, no estilo Dyno/Carl-bot.

Regras: spam, flood repetido, convites, links, menções em massa, CAPS e
palavras proibidas. Cada uma se desliga individualmente.

Como funciona a punição escalonada:
1. A mensagem é apagada e o autor recebe um aviso efêmero no canal.
2. Uma advertência é registrada (mesmo histórico do ``/avisar``).
3. Ao acumular N advertências, o autor leva castigo (timeout) automático.

Desempenho: o listener roda em **toda** mensagem do servidor, então tudo no
caminho quente vem de memória — a configuração sai do cache de guild e o
rastreamento de spam é uma janela deslizante em RAM. Nada de I/O até existir
uma infração de verdade.

Comandos: /automod ativar | regras | palavra | isentar | ver
"""

from datetime import timedelta
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from infra.database import (
    adicionar_palavra_proibida,
    adicionar_warn,
    listar_palavras_proibidas,
    remover_palavra_proibida,
    alternar_isento,
)
from utils.automod import Deteccao, RastreadorDeSpam, Violacao, analisar
from utils.guild_config import guild_config
from utils.logger import get_logger

logger = get_logger(__name__)

# De quanto em quanto tempo o rastreador descarta usuários inativos
MINUTOS_ENTRE_PODAS = 10

SEM_MENCOES = discord.AllowedMentions.none()

# Violações que não fazem sentido punir com advertência acumulada — só
# apagar já resolve, e advertir por CAPS irrita mais do que ajuda.
VIOLACOES_LEVES = {Violacao.CAPS}


class Automod(commands.Cog):
    """Cog de moderação automática."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rastreador = RastreadorDeSpam()

    async def cog_load(self) -> None:
        """Liga a poda periódica do rastreador."""
        self.podar_loop.start()

    async def cog_unload(self) -> None:
        """Para a poda periódica."""
        self.podar_loop.cancel()

    @tasks.loop(minutes=MINUTOS_ENTRE_PODAS)
    async def podar_loop(self):
        """Descarta do rastreador quem não fala há um tempo."""
        removidos = self.rastreador.podar()
        if removidos:
            logger.debug("Automod: %s usuários removidos do rastreador", removidos)

    @podar_loop.before_loop
    async def before_podar(self):
        """Espera o bot ficar pronto."""
        await self.bot.wait_until_ready()

    # --- LISTENER PRINCIPAL ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Analisa cada mensagem e aplica as regras de automod."""
        if message.author.bot or not message.guild:
            return

        config = await guild_config.obter(message.guild.id)
        regras = config.automod
        if not regras.ativo:
            return

        autor = message.author

        # Moderadores nunca são pegos pelo próprio automod
        permissoes = autor.guild_permissions
        if permissoes.manage_messages or permissoes.administrator:
            return

        if config.automod_isento(message.channel.id, {r.id for r in autor.roles}):
            return

        # Janela de spam ajustada à configuração do servidor
        self.rastreador.janela_segundos = regras.spam_janela_segundos
        na_janela, repeticoes = self.rastreador.registrar(
            message.guild.id, autor.id, message.content
        )

        deteccoes = analisar(message.content, regras, na_janela, repeticoes)
        if not deteccoes:
            return

        await self._punir(message, deteccoes, regras)

    async def _punir(
        self,
        message: discord.Message,
        deteccoes: List[Deteccao],
        regras,
    ) -> None:
        """Apaga a mensagem, avisa o autor e escala a punição se necessário."""
        autor = message.author
        motivos = ", ".join(str(d) for d in deteccoes)

        try:
            await message.delete()
        except discord.NotFound:
            pass  # já apagada
        except discord.Forbidden:
            logger.warning(
                "Automod sem permissão para apagar em %s", message.guild.id
            )
            return
        except discord.HTTPException as e:
            logger.warning("Falha ao apagar mensagem do automod: %s", e)

        # Zera a janela para não punir em cascata a mesma rajada
        if any(d.violacao in (Violacao.SPAM, Violacao.FLOOD) for d in deteccoes):
            self.rastreador.limpar_usuario(message.guild.id, autor.id)

        await self._avisar_no_canal(message, motivos)

        # Infrações só leves não geram advertência
        if all(d.violacao in VIOLACOES_LEVES for d in deteccoes):
            await self._registrar_log(message, motivos, castigado=False)
            return

        total = await adicionar_warn(
            message.guild.id, autor.id, self.bot.user.id, f"[automod] {motivos}"
        )

        castigado = False
        if (
            regras.avisos_para_castigo
            and regras.castigo_minutos
            and total >= regras.avisos_para_castigo
            and total % regras.avisos_para_castigo == 0
        ):
            castigado = await self._castigar(message, regras, motivos)

        await self._registrar_log(message, motivos, castigado, total)

    async def _avisar_no_canal(self, message: discord.Message, motivos: str) -> None:
        """Manda um aviso curto no canal e o apaga em seguida."""
        try:
            aviso = await message.channel.send(
                f"🛡️ {message.author.mention}, sua mensagem foi removida: **{motivos}**.",
                allowed_mentions=discord.AllowedMentions(
                    everyone=False, roles=False, users=[message.author]
                ),
                delete_after=8,  # não deixa o canal virar mural de avisos
            )
            del aviso
        except discord.HTTPException:
            logger.debug("Falha ao enviar aviso do automod", exc_info=True)

    async def _castigar(self, message: discord.Message, regras, motivos: str) -> bool:
        """Aplica timeout automático. Retorna True se conseguiu."""
        autor = message.author

        if autor.top_role >= message.guild.me.top_role:
            logger.info(
                "Automod não castigou %s: cargo acima do bot", autor.id
            )
            return False

        try:
            await autor.timeout(
                timedelta(minutes=regras.castigo_minutos),
                reason=f"[automod] {motivos}",
            )
        except discord.Forbidden:
            logger.warning("Automod sem permissão para castigar em %s", message.guild.id)
            return False
        except discord.HTTPException as e:
            logger.warning("Falha ao castigar via automod: %s", e)
            return False

        try:
            await autor.send(
                f"🔇 Você recebeu **{regras.castigo_minutos} min** de castigo em "
                f"**{message.guild.name}** por infrações repetidas: {motivos}"
            )
        except discord.HTTPException:
            pass  # DMs fechadas

        return True

    async def _registrar_log(
        self,
        message: discord.Message,
        motivos: str,
        castigado: bool,
        total_avisos: Optional[int] = None,
    ) -> None:
        """Registra a ação no canal de logs configurado."""
        config = await guild_config.obter(message.guild.id)
        if not config.log_channel_id:
            return

        canal = message.guild.get_channel(config.log_channel_id)
        if canal is None:
            return

        embed = discord.Embed(
            title="🛡️ Automod",
            description=(message.content[:1000] or "_(sem texto)_"),
            color=discord.Color.dark_orange(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(
            name=f"{message.author} ({message.author.id})",
            icon_url=message.author.display_avatar.url,
        )
        embed.add_field(name="Motivo", value=motivos, inline=False)
        embed.add_field(name="Canal", value=message.channel.mention, inline=True)

        if total_avisos is not None:
            embed.add_field(name="Avisos", value=str(total_avisos), inline=True)
        if castigado:
            embed.add_field(name="Ação", value="🔇 Castigo aplicado", inline=True)

        try:
            await canal.send(embed=embed, allowed_mentions=SEM_MENCOES)
        except discord.HTTPException as e:
            logger.warning("Falha ao registrar log do automod: %s", e)

    # --- COMANDOS ---

    automod = app_commands.Group(
        name="automod",
        description="Moderação automática de mensagens",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    @automod.command(name="ativar", description="Liga ou desliga o automod")
    @app_commands.describe(ativo="True para ligar, False para desligar")
    async def automod_ativar(self, interaction: discord.Interaction, ativo: bool):
        """Liga/desliga o automod no servidor."""
        await guild_config.atualizar(interaction.guild.id, automod_ativo=int(ativo))

        if not ativo:
            return await interaction.response.send_message(
                "🛡️ Automod **desligado**.", ephemeral=True
            )

        permissoes = interaction.guild.me.guild_permissions
        faltando = []
        if not permissoes.manage_messages:
            faltando.append("Gerenciar Mensagens")
        if not permissoes.moderate_members:
            faltando.append("Moderar Membros (para o castigo automático)")

        aviso = (
            f"\n⚠️ Faltam permissões para mim: **{', '.join(faltando)}**."
            if faltando
            else ""
        )
        await interaction.response.send_message(
            f"🛡️ Automod **ligado**. Veja as regras com `/automod ver`.{aviso}",
            ephemeral=True,
        )

    @automod.command(name="regras", description="Ajusta os limites do automod")
    @app_commands.describe(
        spam_mensagens="Máx. de mensagens na janela (0 desliga)",
        spam_janela="Tamanho da janela de spam em segundos",
        flood="Repetições da mesma mensagem (0 desliga)",
        convites="Bloquear convites de outros servidores",
        links="Bloquear qualquer link",
        mencoes="Máx. de menções por mensagem (0 desliga)",
        caps="% de maiúsculas para bloquear (0 desliga)",
        castigo_minutos="Duração do castigo automático (0 desliga)",
        avisos_para_castigo="Avisos até o castigo automático",
    )
    async def automod_regras(
        self,
        interaction: discord.Interaction,
        spam_mensagens: Optional[app_commands.Range[int, 0, 30]] = None,
        spam_janela: Optional[app_commands.Range[int, 1, 60]] = None,
        flood: Optional[app_commands.Range[int, 0, 20]] = None,
        convites: Optional[bool] = None,
        links: Optional[bool] = None,
        mencoes: Optional[app_commands.Range[int, 0, 50]] = None,
        caps: Optional[app_commands.Range[int, 0, 100]] = None,
        castigo_minutos: Optional[app_commands.Range[int, 0, 40320]] = None,
        avisos_para_castigo: Optional[app_commands.Range[int, 0, 20]] = None,
    ):
        """Ajusta um ou mais limites do automod."""
        campos = {
            "automod_spam_mensagens": spam_mensagens,
            "automod_spam_janela": spam_janela,
            "automod_flood": flood,
            "automod_convites": None if convites is None else int(convites),
            "automod_links": None if links is None else int(links),
            "automod_mencoes": mencoes,
            "automod_caps": caps,
            "automod_castigo_minutos": castigo_minutos,
            "automod_avisos_castigo": avisos_para_castigo,
        }
        alterados = {k: v for k, v in campos.items() if v is not None}

        if not alterados:
            return await interaction.response.send_message(
                "ℹ️ Informe pelo menos um limite para alterar.", ephemeral=True
            )

        await guild_config.atualizar(interaction.guild.id, **alterados)
        await interaction.response.send_message(
            f"✅ {len(alterados)} regra(s) atualizada(s). Veja com `/automod ver`.",
            ephemeral=True,
        )

    @automod.command(name="palavra", description="Gerencia a lista de palavras proibidas")
    @app_commands.describe(acao="O que fazer", palavra="A palavra (não use em 'listar')")
    @app_commands.choices(
        acao=[
            app_commands.Choice(name="➕ Adicionar", value="add"),
            app_commands.Choice(name="➖ Remover", value="remove"),
            app_commands.Choice(name="📜 Listar", value="list"),
        ]
    )
    async def automod_palavra(
        self,
        interaction: discord.Interaction,
        acao: app_commands.Choice[str],
        palavra: Optional[str] = None,
    ):
        """Adiciona, remove ou lista palavras proibidas."""
        guild_id = interaction.guild.id

        if acao.value == "list":
            palavras = await listar_palavras_proibidas(guild_id)
            if not palavras:
                return await interaction.response.send_message(
                    "ℹ️ Nenhuma palavra proibida configurada.", ephemeral=True
                )

            embed = discord.Embed(
                title=f"🚫 Palavras proibidas ({len(palavras)})",
                description=", ".join(f"||{p}||" for p in palavras)[:4000],
                color=discord.Color.red(),
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if not palavra or not palavra.strip():
            return await interaction.response.send_message(
                "❌ Informe a palavra.", ephemeral=True
            )

        if acao.value == "add":
            adicionada = await adicionar_palavra_proibida(guild_id, palavra)
            guild_config.invalidar(guild_id)
            mensagem = (
                f"✅ `{palavra}` adicionada à lista."
                if adicionada
                else f"ℹ️ `{palavra}` já estava na lista."
            )
        else:
            removida = await remover_palavra_proibida(guild_id, palavra)
            guild_config.invalidar(guild_id)
            mensagem = (
                f"✅ `{palavra}` removida da lista."
                if removida
                else f"❌ `{palavra}` não estava na lista."
            )

        await interaction.response.send_message(mensagem, ephemeral=True)

    @automod.command(name="isentar", description="Isenta um canal ou cargo do automod")
    @app_commands.describe(canal="Canal a isentar", cargo="Cargo a isentar")
    async def automod_isentar(
        self,
        interaction: discord.Interaction,
        canal: Optional[discord.TextChannel] = None,
        cargo: Optional[discord.Role] = None,
    ):
        """Alterna a isenção de um canal ou cargo."""
        if canal is None and cargo is None:
            return await interaction.response.send_message(
                "❌ Informe um canal ou um cargo.", ephemeral=True
            )

        partes = []

        if canal is not None:
            isento = await alternar_isento(interaction.guild.id, canal.id, "canal")
            partes.append(
                f"{canal.mention} {'agora é isento' if isento else 'deixou de ser isento'}"
            )

        if cargo is not None:
            isento = await alternar_isento(interaction.guild.id, cargo.id, "cargo")
            partes.append(
                f"**{cargo.name}** {'agora é isento' if isento else 'deixou de ser isento'}"
            )

        guild_config.invalidar(interaction.guild.id)
        await interaction.response.send_message(
            "🛡️ " + " • ".join(partes), ephemeral=True, allowed_mentions=SEM_MENCOES
        )

    @automod.command(name="ver", description="Mostra a configuração atual do automod")
    async def automod_ver(self, interaction: discord.Interaction):
        """Exibe todas as regras e isenções."""
        config = await guild_config.obter(interaction.guild.id)
        regras = config.automod

        def limite(valor: int, sufixo: str = "") -> str:
            return f"{valor}{sufixo}" if valor else "desligado"

        embed = discord.Embed(
            title="🛡️ Configuração do Automod",
            color=discord.Color.green() if regras.ativo else discord.Color.greyple(),
        )
        embed.add_field(
            name="Estado",
            value="🟢 Ligado" if regras.ativo else "🔴 Desligado",
            inline=False,
        )
        embed.add_field(
            name="Spam",
            value=limite(regras.spam_mensagens, f" msgs / {regras.spam_janela_segundos}s"),
            inline=True,
        )
        embed.add_field(
            name="Flood", value=limite(regras.flood_repeticoes, "x igual"), inline=True
        )
        embed.add_field(
            name="Menções", value=limite(regras.max_mencoes, " por msg"), inline=True
        )
        embed.add_field(
            name="Convites", value="🚫 bloqueados" if regras.bloquear_convites else "permitidos",
            inline=True,
        )
        embed.add_field(
            name="Links", value="🚫 bloqueados" if regras.bloquear_links else "permitidos",
            inline=True,
        )
        embed.add_field(name="CAPS", value=limite(regras.caps_percentual, "%"), inline=True)
        embed.add_field(
            name="Castigo automático",
            value=(
                f"{regras.castigo_minutos} min após {regras.avisos_para_castigo} avisos"
                if regras.castigo_minutos and regras.avisos_para_castigo
                else "desligado"
            ),
            inline=False,
        )
        embed.add_field(
            name="Palavras proibidas",
            value=f"{len(regras.palavras_proibidas)} cadastradas",
            inline=True,
        )
        embed.add_field(
            name="Isenções",
            value=(
                f"{len(config.automod_canais_isentos)} canais, "
                f"{len(config.automod_cargos_isentos)} cargos"
            ),
            inline=True,
        )
        embed.set_footer(
            text="Moderadores (Gerenciar Mensagens) nunca são afetados pelo automod"
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Automod(bot))

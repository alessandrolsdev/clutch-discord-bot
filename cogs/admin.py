"""
COG: ADMIN (DONO DO BOT)
========================

Ferramentas de operação, restritas ao dono da aplicação.

Por que ``!sync`` é um comando de **prefixo** e não um slash command:
para usar um slash command ele precisa já estar sincronizado — e o problema
que ``!sync`` resolve é justamente o de sincronizar. Um comando de prefixo
funciona assim que o bot conecta, sem depender de sync nenhum.

Comandos: !sync !cogs !reload !backup !cache !info
"""

import asyncio
import time
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands, tasks

from config.settings import settings
from infra.backup import criar_backup, listar_backups
from utils.guild_config import guild_config
from utils.logger import get_logger

logger = get_logger(__name__)

# Intervalo do backup automático
HORAS_ENTRE_BACKUPS = 24


class Admin(commands.Cog):
    """Cog de operação, só para o dono do bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.iniciado_em = time.time()

    async def cog_load(self) -> None:
        """Liga o backup automático, se habilitado."""
        if settings.database.backup_enabled:
            self.backup_loop.start()

    async def cog_unload(self) -> None:
        """Para o loop de backup."""
        self.backup_loop.cancel()

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Restringe todos os comandos deste cog ao dono da aplicação."""
        return await self.bot.is_owner(ctx.author)

    # --- BACKUP AUTOMÁTICO ---

    @tasks.loop(hours=HORAS_ENTRE_BACKUPS)
    async def backup_loop(self):
        """Gera um backup diário do banco."""
        # sqlite3.backup é bloqueante: vai para uma thread
        await asyncio.to_thread(
            criar_backup,
            settings.database.db_path,
            settings.database.backup_dir,
            settings.database.backup_keep,
        )

    @backup_loop.before_loop
    async def before_backup(self):
        """Espera o bot ficar pronto antes do primeiro backup."""
        await self.bot.wait_until_ready()

    # --- COMANDOS ---

    @commands.command(name="sync")
    async def sync(self, ctx: commands.Context, escopo: Optional[str] = None):
        """
        Sincroniza os slash commands com o Discord.

        Uso:
            !sync          - servidor atual (instantâneo)
            !sync global   - todos os servidores (pode levar até 1h)
            !sync limpar   - remove os comandos deste servidor
        """
        escopo = (escopo or "guild").lower()

        async with ctx.typing():
            try:
                if escopo in ("global", "todos"):
                    comandos = await self.bot.tree.sync()
                    destino = "globalmente"

                elif escopo in ("limpar", "clear"):
                    if ctx.guild is None:
                        return await ctx.send("❌ Use dentro de um servidor.")
                    self.bot.tree.clear_commands(guild=ctx.guild)
                    await self.bot.tree.sync(guild=ctx.guild)
                    return await ctx.send("🧹 Comandos removidos deste servidor.")

                else:
                    if ctx.guild is None:
                        return await ctx.send("❌ Use dentro de um servidor.")
                    # copy_global_to publica os comandos globais na guild,
                    # que propaga na hora (o sync global demora até 1h)
                    self.bot.tree.copy_global_to(guild=ctx.guild)
                    comandos = await self.bot.tree.sync(guild=ctx.guild)
                    destino = f"em {ctx.guild.name}"

            except discord.HTTPException as e:
                logger.error("Falha no sync: %s", e)
                return await ctx.send(f"❌ Falha no sync: {e}")

        await ctx.send(f"🌲 **{len(comandos)}** comandos sincronizados {destino}.")
        logger.info("Sync manual: %s comandos %s", len(comandos), destino)

    @commands.command(name="cogs")
    async def cogs(self, ctx: commands.Context):
        """Lista os cogs carregados."""
        carregados = sorted(self.bot.extensions)
        linhas = "\n".join(f"`{nome}`" for nome in carregados)

        embed = discord.Embed(
            title=f"⚙️ Cogs carregados ({len(carregados)})",
            description=linhas or "_nenhum_",
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="reload")
    async def reload(self, ctx: commands.Context, nome: str):
        """
        Recarrega um cog sem reiniciar o bot.

        Uso: !reload musica
        """
        extensao = nome if nome.startswith("cogs.") else f"cogs.{nome}"

        try:
            await self.bot.reload_extension(extensao)
        except commands.ExtensionNotLoaded:
            try:
                await self.bot.load_extension(extensao)
            except commands.ExtensionError as e:
                return await ctx.send(f"❌ Falha ao carregar `{extensao}`: {e}")
            return await ctx.send(f"✅ `{extensao}` carregado.")
        except commands.ExtensionError as e:
            logger.error("Falha ao recarregar %s: %s", extensao, e, exc_info=True)
            return await ctx.send(f"❌ Falha ao recarregar `{extensao}`: {e}")

        # O cache de config pode ter sido montado com dados do cog antigo
        guild_config.limpar()
        await ctx.send(f"♻️ `{extensao}` recarregado.")

    @commands.command(name="backup")
    async def backup(self, ctx: commands.Context):
        """Gera um backup do banco agora."""
        async with ctx.typing():
            destino = await asyncio.to_thread(
                criar_backup,
                settings.database.db_path,
                settings.database.backup_dir,
                settings.database.backup_keep,
            )

        if destino is None:
            return await ctx.send("❌ Não foi possível gerar o backup (veja os logs).")

        tamanho_kb = destino.stat().st_size / 1024
        existentes = listar_backups(Path(settings.database.backup_dir))

        await ctx.send(
            f"💾 Backup criado: `{destino.name}` ({tamanho_kb:.1f} KB)\n"
            f"Backups guardados: **{len(existentes)}** "
            f"(mantendo {settings.database.backup_keep})"
        )

    @commands.command(name="backups")
    async def backups(self, ctx: commands.Context):
        """Lista os backups existentes."""
        arquivos = listar_backups(Path(settings.database.backup_dir))

        if not arquivos:
            return await ctx.send("ℹ️ Nenhum backup ainda. Use `!backup`.")

        linhas = "\n".join(
            f"`{a.name}` — {a.stat().st_size / 1024:.1f} KB" for a in arquivos[:15]
        )
        embed = discord.Embed(
            title=f"💾 Backups ({len(arquivos)})",
            description=linhas,
            color=discord.Color.green(),
        )
        embed.set_footer(text=f"Pasta: {settings.database.backup_dir}")
        await ctx.send(embed=embed)

    @commands.command(name="cache")
    async def cache(self, ctx: commands.Context, acao: Optional[str] = None):
        """
        Mostra ou limpa o cache de configuração.

        Uso: !cache  ou  !cache limpar
        """
        if acao and acao.lower() in ("limpar", "clear"):
            guild_config.limpar()
            return await ctx.send("🧹 Cache de configuração limpo.")

        await ctx.send(
            f"📦 Config em cache: **{guild_config.tamanho}** servidores "
            f"(de {len(self.bot.guilds)} conectados)."
        )

    @commands.command(name="info")
    async def info(self, ctx: commands.Context):
        """Resumo operacional do bot."""
        total_comandos = len(self.bot.tree.get_commands())
        uptime = int(time.time() - self.iniciado_em)

        embed = discord.Embed(title="🤖 Clutch — Info", color=discord.Color.blurple())
        embed.add_field(name="Versão", value=settings.version, inline=True)
        embed.add_field(name="Servidores", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Latência", value=f"{self.bot.latency * 1000:.0f}ms", inline=True)
        embed.add_field(name="Cogs", value=str(len(self.bot.extensions)), inline=True)
        embed.add_field(name="Slash commands", value=str(total_comandos), inline=True)
        embed.add_field(name="Uptime do cog", value=f"{uptime // 60} min", inline=True)
        embed.add_field(
            name="Sync",
            value=f"Dev guild: `{settings.bot.dev_guild_id or 'global'}`\n"
            f"Auto-sync: `{settings.bot.auto_sync}`",
            inline=False,
        )
        embed.add_field(
            name="Backup",
            value=f"`{settings.database.backup_dir}` • "
            f"{'ligado' if settings.database.backup_enabled else 'desligado'} • "
            f"mantém {settings.database.backup_keep}",
            inline=False,
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))

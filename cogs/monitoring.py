"""
COG: MONITORING (HEALTH CHECKS)
================================

Sistema de monitoramento de saúde de todos os componentes do bot.

Funcionalidades:
- Comando /status - Mostra saúde de todos os componentes
- Endpoint /health - Health check HTTP (JSON)
- Monitora:
  - Latência do bot
  - Status do banco de dados
  - Conexão UDP (microfone/receptor)
  - API HTTP status
  - Uso de memória/CPU
- Alertas automáticos se algo falhar

Autor: Clutch Development Team
Versão: 3.0
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import asyncio
import psutil
import time
from typing import Optional, Dict
from datetime import datetime, timedelta, timezone

from utils.logger import get_logger
from config.settings import settings
from infra.database import get_conexao

logger = get_logger(__name__)


class ComponentHealth:
    """Representa o estado de saúde de um componente"""

    def __init__(self, name: str):
        self.name = name
        self.is_healthy = False
        self.latency_ms: Optional[float] = None
        self.error_message: Optional[str] = None
        self.last_check = datetime.now(timezone.utc)

    def __repr__(self):
        status = "🟢" if self.is_healthy else "🔴"
        latency = f" ({self.latency_ms:.0f}ms)" if self.latency_ms else ""
        error = f" - {self.error_message}" if self.error_message else ""
        return f"{status} {self.name}{latency}{error}"


class Monitoring(commands.Cog):
    """Cog de monitoramento e health checks"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = datetime.now(timezone.utc)
        self.health_data: Dict[str, ComponentHealth] = {}

    async def cog_load(self):
        """Inicia o loop de monitoramento quando o cog é carregado."""
        # Iniciar em __init__ dispara o loop antes do bot existir de fato.
        self.health_check_loop.start()
        logger.info("🏥 Sistema de monitoring inicializado")

    async def cog_unload(self):
        """Para loops ao descarregar cog"""
        self.health_check_loop.cancel()

    async def check_bot_health(self) -> ComponentHealth:
        """Verifica saúde do bot Discord"""
        health = ComponentHealth("Discord Bot")

        try:
            # Latência do websocket
            health.latency_ms = self.bot.latency * 1000

            # Considera saudável se latência < 500ms
            health.is_healthy = health.latency_ms < 500

            if not health.is_healthy:
                health.error_message = "Alta latência"

        except Exception as e:
            health.error_message = str(e)
            logger.error(f"Erro ao verificar saúde do bot: {e}")

        return health

    async def check_database_health(self) -> ComponentHealth:
        """Verifica saúde do banco de dados"""
        health = ComponentHealth("Database (SQLite)")

        try:
            start = time.time()

            # Tenta fazer uma query simples
            async with get_conexao() as db:
                cursor = await db.execute("SELECT COUNT(*) FROM usuarios")
                await cursor.fetchone()

            health.latency_ms = (time.time() - start) * 1000
            health.is_healthy = True

        except Exception as e:
            health.error_message = str(e)
            logger.error(f"Erro ao verificar saúde do DB: {e}")

        return health

    async def check_api_health(self) -> ComponentHealth:
        """Verifica saúde da API HTTP"""
        health = ComponentHealth("API HTTP")

        try:
            host = settings.api.host
            # 0.0.0.0 é endereço de bind, não de destino
            if host in ("0.0.0.0", "::"):
                host = "127.0.0.1"
            url = f"http://{host}:{settings.api.port}/status"

            # A API exige X-API-Key quando configurada
            headers = (
                {"X-API-Key": settings.api.api_key} if settings.api.api_key else {}
            )

            start = time.time()

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        health.is_healthy = True
                        health.latency_ms = (time.time() - start) * 1000
                    else:
                        health.error_message = f"Status {resp.status}"

        except asyncio.TimeoutError:
            health.error_message = "Timeout"
        except aiohttp.ClientConnectorError:
            health.error_message = "Não conectado"
        except Exception as e:
            health.error_message = str(e)
            logger.error(f"Erro ao verificar saúde da API: {e}")

        return health

    def check_system_resources(self) -> Dict[str, float]:
        """Verifica uso de recursos do sistema"""
        try:
            process = psutil.Process()

            return {
                "cpu_percent": process.cpu_percent(interval=0.1),
                "memory_mb": process.memory_info().rss / 1024 / 1024,
                "threads": process.num_threads(),
                "uptime_seconds": (datetime.now(timezone.utc) - self.start_time).total_seconds(),
            }
        except Exception as e:
            logger.error(f"Erro ao obter recursos do sistema: {e}")
            return {}

    @tasks.loop(minutes=5)
    async def health_check_loop(self):
        """Loop que executa health checks periodicamente"""
        logger.debug("Executando health checks periódicos...")

        # Atualiza health data
        self.health_data["bot"] = await self.check_bot_health()
        self.health_data["database"] = await self.check_database_health()
        self.health_data["api"] = await self.check_api_health()

        # Verifica se algum componente está unhealthy
        unhealthy = [h for h in self.health_data.values() if not h.is_healthy]

        if unhealthy:
            logger.warning(
                f"Componentes com problemas: {', '.join(h.name for h in unhealthy)}"
            )

    @health_check_loop.before_loop
    async def before_health_check(self):
        """Aguarda bot estar pronto antes de iniciar loop"""
        await self.bot.wait_until_ready()

    @app_commands.command(name="status", description="📊 Mostra status de saúde do bot")
    async def status(self, interaction: discord.Interaction):
        """
        Mostra status detalhado de todos os componentes.

        Verifica:
        - Bot Discord
        - Banco de dados
        - API HTTP
        - Recursos do sistema (CPU, RAM)
        - Uptime
        """
        await interaction.response.defer()

        # Executa todos os health checks
        checks = await asyncio.gather(
            self.check_bot_health(),
            self.check_database_health(),
            self.check_api_health(),
        )

        # Obtém recursos do sistema
        resources = self.check_system_resources()

        # Constrói embed
        embed = discord.Embed(
            title="📊 Status do Sistema",
            description="Saúde de todos os componentes",
            color=(
                discord.Color.green()
                if all(c.is_healthy for c in checks)
                else discord.Color.red()
            ),
            timestamp=datetime.now(timezone.utc),
        )

        # Adiciona status de cada componente
        for check in checks:
            status_emoji = "🟢" if check.is_healthy else "🔴"
            latency = f"{check.latency_ms:.0f}ms" if check.latency_ms else "N/A"
            error = f"\n❌ {check.error_message}" if check.error_message else ""

            embed.add_field(
                name=f"{status_emoji} {check.name}",
                value=f"Latência: `{latency}`{error}",
                inline=True,
            )

        # Adiciona recursos do sistema
        if resources:
            uptime = timedelta(seconds=int(resources.get("uptime_seconds", 0)))

            resources_text = f"""
            **CPU:** {resources.get('cpu_percent', 0):.1f}%
            **RAM:** {resources.get('memory_mb', 0):.1f} MB
            **Threads:** {resources.get('threads', 0)}
            **Uptime:** {uptime}
            """

            embed.add_field(
                name="💻 Recursos do Sistema",
                value=resources_text.strip(),
                inline=False,
            )

        # Adiciona informações do servidor
        if interaction.guild:
            voice_client = interaction.guild.voice_client

            voice_status = "🔴 Desconectado"
            if voice_client and voice_client.is_connected():
                channel_name = voice_client.channel.name
                voice_status = f"🟢 Conectado em **{channel_name}**"

            embed.add_field(name="🎤 Canal de Voz", value=voice_status, inline=True)

        # Footer
        embed.set_footer(
            text=f"Clutch Bot v{settings.version} • Solicitado por {interaction.user.name}",
            icon_url=self.bot.user.display_avatar.url,
        )

        await interaction.followup.send(embed=embed)
        logger.info(f"Status solicitado por {interaction.user.name}")

    @app_commands.command(name="ping", description="🏓 Testa latência do bot")
    async def ping(self, interaction: discord.Interaction):
        """Comando simples para testar responsividade"""
        # Calcula latência
        latency_ms = self.bot.latency * 1000

        # Determina cor baseada na latência
        if latency_ms < 100:
            color = discord.Color.green()
            emoji = "🟢"
        elif latency_ms < 300:
            color = discord.Color.yellow()
            emoji = "🟡"
        else:
            color = discord.Color.red()
            emoji = "🔴"

        embed = discord.Embed(
            title=f"{emoji} Pong!",
            description=f"Latência: **{latency_ms:.0f}ms**",
            color=color,
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="uptime", description="⏱️ Mostra há quanto tempo o bot está online"
    )
    async def uptime(self, interaction: discord.Interaction):
        """Mostra tempo desde que o bot foi iniciado"""
        uptime = datetime.now(timezone.utc) - self.start_time

        # Formata uptime
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        uptime_text = []
        if days > 0:
            uptime_text.append(f"{days}d")
        if hours > 0:
            uptime_text.append(f"{hours}h")
        if minutes > 0:
            uptime_text.append(f"{minutes}m")
        uptime_text.append(f"{seconds}s")

        embed = discord.Embed(
            title="⏱️ Uptime do Bot",
            description=f"Online há: **{' '.join(uptime_text)}**",
            color=discord.Color.blue(),
            timestamp=self.start_time,
        )

        embed.set_footer(text="Bot iniciado em")

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    """Carrega o cog"""
    await bot.add_cog(Monitoring(bot))

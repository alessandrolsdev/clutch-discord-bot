"""
CLUTCH DISCORD BOT V3.0
=======================

Bot Discord avançado com funcionalidades de:
- 🎵 Reprodução de música do YouTube com controles interativos
- 🎙️ Sistema de áudio em tempo real com modulação de voz
- 🤖 Integração com Google Gemini AI para chat inteligente
- 🏆 Sistema de níveis, XP e conquistas gamificadas
- 📊 Dashboard web (Streamlit) para controle remoto
- 🔊 Text-to-Speech (TTS) com vozes em português
- 🎛️ Soundboard e efeitos sonoros personalizados
- 👀 Sistema de moderação e logs automáticos

Desenvolvido para criar experiências imersivas em servidores Discord.

Autor: Clutch Development Team
Versão: 3.0
Python: 3.10+
"""

import asyncio
import random
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config.settings import settings
from infra.database import inicializar_db
from utils.guild_config import guild_config
from utils.logger import get_logger

logger = get_logger(__name__)

# Intents (permissões do bot)
# Necessário para ler conteúdo de mensagens, membros e estados de voz
intents = discord.Intents.default()
intents.message_content = True  # Ler conteúdo de mensagens (para comandos e XP)
intents.members = True  # Rastrear entrada/saída de membros
intents.voice_states = True  # Detectar quando membros entram/saem de canais de voz
intents.presences = True  # Receber status/activity em tempo real dos membros

COGS_DIR = Path(__file__).parent / "cogs"


class ClutchBot(commands.Bot):
    """
    Classe principal do bot Clutch.

    Herda de commands.Bot e adiciona funcionalidades personalizadas como:
    - Carregamento automático de cogs (módulos)
    - Sistema de status rotativo
    - Sincronização de slash commands
    """

    def __init__(self):
        """Inicializa o bot com as configurações de config/settings.py."""
        super().__init__(
            command_prefix=settings.bot.prefix,
            intents=intents,
            help_command=None,
        )
        self.status_loop.change_interval(seconds=settings.bot.status_rotation_seconds)
        # Erros de slash command (cooldown, permissão) precisam de tratamento
        # próprio: a árvore de app commands não usa on_command_error.
        self.tree.on_error = self.on_app_command_error

    async def setup_hook(self):
        """
        Hook executado durante a inicialização do bot (antes de conectar).

        Responsabilidades:
        1. Inicializar o banco de dados
        2. Carregar todas as extensões (cogs) da pasta /cogs
        3. Sincronizar slash commands com o Discord
        4. Iniciar loop de rotação de status
        """
        # O banco precisa existir antes dos cogs começarem a consultá-lo.
        await inicializar_db()

        # Carrega extensões automaticamente (ordem estável entre ambientes)
        carregados, falhas = 0, 0
        for arquivo in sorted(COGS_DIR.glob("*.py")):
            if arquivo.name == "__init__.py":
                continue
            try:
                await self.load_extension(f"cogs.{arquivo.stem}")
                logger.info("⚙️  Cog carregado: %s", arquivo.name)
                carregados += 1
            except Exception as e:
                # exc_info dá o traceback real em vez de só a mensagem
                logger.error("❌ Erro ao carregar %s: %s", arquivo.name, e, exc_info=True)
                falhas += 1

        logger.info("Cogs: %s carregados, %s com falha", carregados, falhas)

        # Sincroniza Slash Commands com o Discord
        try:
            comandos = await self.tree.sync()
            logger.info("🌲 %s slash commands sincronizados", len(comandos))
        except Exception as e:
            logger.error("❌ Erro no sync de slash commands: %s", e, exc_info=True)

        # Inicia loop de status
        self.status_loop.start()

    async def on_ready(self):
        """Evento disparado quando o bot conecta com sucesso ao Discord."""
        logger.info(
            "✅ CLUTCH v%s ONLINE como %s (%s servidores)",
            settings.version,
            self.user,
            len(self.guilds),
        )

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        """
        Trata erros de slash commands com mensagens amigáveis.

        Sem isso, um cooldown ou falta de permissão vira um traceback no log e
        um "aplicação não respondeu" para o usuário.
        """
        if isinstance(error, app_commands.CommandOnCooldown):
            mensagem = (
                f"⏳ Calma! Tente de novo em **{error.retry_after:.0f}s**."
            )
        elif isinstance(error, app_commands.MissingPermissions):
            mensagem = "❌ Você não tem permissão para usar este comando."
        elif isinstance(error, app_commands.BotMissingPermissions):
            faltando = ", ".join(error.missing_permissions)
            mensagem = f"❌ Faltam permissões para mim: `{faltando}`."
        elif isinstance(error, app_commands.NoPrivateMessage):
            mensagem = "❌ Este comando só funciona em servidores."
        elif isinstance(error, app_commands.CheckFailure):
            mensagem = "❌ Você não pode usar este comando aqui."
        else:
            logger.error(
                "Erro no comando /%s: %s",
                interaction.command.name if interaction.command else "?",
                error,
                exc_info=error,
            )
            mensagem = "❌ Deu ruim aqui. O erro foi registrado nos logs."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(mensagem, ephemeral=True)
            else:
                await interaction.response.send_message(mensagem, ephemeral=True)
        except discord.HTTPException:
            logger.debug("Não foi possível responder ao erro da interação")

    async def on_guild_remove(self, guild: discord.Guild):
        """Libera o cache de configuração de servidores que removeram o bot."""
        guild_config.invalidar(guild.id)

    async def on_command_error(self, ctx, error):
        """Evita que erros de comandos legados fiquem silenciosos."""
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Você não tem permissão para usar este comando.")
            return
        logger.error("Erro no comando %s: %s", ctx.command, error, exc_info=error)

    @tasks.loop(seconds=60)
    async def status_loop(self):
        """
        Loop que muda o status do bot periodicamente.

        Seleciona um status aleatório da lista para dar dinamismo
        e mostrar diferentes atividades que o bot pode fazer.
        """
        tipos = [
            discord.ActivityType.listening,
            discord.ActivityType.playing,
            discord.ActivityType.watching,
            discord.ActivityType.competing,
        ]
        nome = random.choice(settings.bot.status_messages)
        try:
            await self.change_presence(
                activity=discord.Activity(type=random.choice(tipos), name=nome)
            )
        except discord.HTTPException as e:
            # Uma falha de rede aqui não deve derrubar o loop de status
            logger.warning("Não foi possível atualizar o status: %s", e)

    @status_loop.before_loop
    async def before_status_loop(self):
        """
        Garante que o bot está pronto antes de iniciar o loop de status.
        Previne erros ao tentar mudar status antes de conectar.
        """
        await self.wait_until_ready()

    async def close(self):
        """Encerra o loop de status antes de fechar a conexão."""
        self.status_loop.cancel()
        await super().close()


def main() -> None:
    """
    Ponto de entrada principal da aplicação.

    O token já é validado em config/settings.py (DISCORD_TOKEN é obrigatório),
    então aqui só resta subir o bot e tratar interrupção manual.
    """
    bot = ClutchBot()
    try:
        bot.run(settings.bot.token, log_handler=None)
    except discord.LoginFailure:
        logger.critical(
            "❌ Token do Discord inválido. Confira DISCORD_TOKEN no seu .env."
        )
        raise SystemExit(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("🛑 Bot desligado.")


if __name__ == "__main__":
    main()

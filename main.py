"""
CLUTCH DISCORD BOT V2.5
======================

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
Versão: 2.5
Python: 3.8+
"""

import os
import asyncio
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from infra.database import inicializar_db
import random
from typing import Optional

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()
TOKEN: Optional[str] = os.getenv("DISCORD_TOKEN")

# Configuração de Pastas (cria se não existirem)
os.makedirs("cogs", exist_ok=True)
os.makedirs("data", exist_ok=True)
os.makedirs("assets/sfx", exist_ok=True)

# Intents (permissões do bot)
# Necessário para ler conteúdo de mensagens, membros e estados de voz
intents = discord.Intents.default()
intents.message_content = True  # Ler conteúdo de mensagens (para comandos e XP)
intents.members = True  # Rastrear entrada/saída de membros
intents.voice_states = True  # Detectar quando membros entram/saem de canais de voz


class ClutchBot(commands.Bot):
    """
    Classe principal do bot Clutch.

    Herda de commands.Bot e adiciona funcionalidades personalizadas como:
    - Carregamento automático de cogs (módulos)
    - Sistema de status rotativo
    - Sincronização de slash commands
    """

    def __init__(self):
        """
        Inicializa o bot com configurações básicas.

        - Prefixo de comando: ! (para comandos legados)
        - Intents configurados acima
        - Remove comando de ajuda padrão (temos um customizado)
        """
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        """
        Hook executado durante a inicialização do bot (antes de conectar).

        Responsabilidades:
        1. Carregar todas as extensões (cogs) da pasta /cogs
        2. Sincronizar slash commands com o Discord
        3. Iniciar loop de rotação de status
        """
        # Carrega extensões automaticamente
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py") and filename != "__init__.py":
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                    print(f"⚙️  Cog Carregado: {filename}")
                except Exception as e:
                    print(f"❌ Erro ao carregar {filename}: {e}")

        # Sincroniza Slash Commands com o Discord
        # Isso permite que os comandos apareçam na interface do Discord
        try:
            await self.tree.sync()
            print("🌲 Slash Commands Sincronizados!")
        except Exception as e:
            print(f"❌ Erro no Sync: {e}")

        # Inicia loop de status (muda a cada 60 segundos)
        self.status_loop.start()

    async def on_ready(self):
        """
        Evento disparado quando o bot conecta com sucesso ao Discord.

        Inicializa o banco de dados e exibe informações de conexão.
        """
        print("---")
        print(f"✅ CLUTCH V2.5 ONLINE: {self.user.name}")
        await inicializar_db()
        print("---")

    @tasks.loop(seconds=60)
    async def status_loop(self):
        """
        Loop que muda o status do bot a cada 60 segundos.

        Seleciona um status aleatório da lista para dar dinamismo
        e mostrar diferentes atividades que o bot pode fazer.
        """
        status_list = [
            discord.Activity(type=discord.ActivityType.listening, name="Spotify"),
            discord.Activity(type=discord.ActivityType.playing, name="RPG de Mesa"),
            discord.Activity(type=discord.ActivityType.watching, name="o servidor"),
            discord.Activity(type=discord.ActivityType.competing, name="pelo Top 1"),
            discord.Game(name="Clutch OS v2.5"),
        ]
        await self.change_presence(activity=random.choice(status_list))

    @status_loop.before_loop
    async def before_status_loop(self):
        """
        Garante que o bot está pronto antes de iniciar o loop de status.
        Previne erros ao tentar mudar status antes de conectar.
        """
        await self.wait_until_ready()


# Instância global do bot
bot = ClutchBot()

if __name__ == "__main__":
    """
    Ponto de entrada principal da aplicação.

    Valida que o token existe e inicia o bot.
    Trata interrupção manual (Ctrl+C) de forma elegante.
    """
    if TOKEN:
        try:
            bot.run(TOKEN)
        except KeyboardInterrupt:
            print("\n🛑 Bot desligado.")
    else:
        print("❌ ERRO: Token não encontrado no .env")
        print("   Dica: Copie .env.example para .env e adicione seu token")

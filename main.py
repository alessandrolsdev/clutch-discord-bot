import os
import asyncio
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from infra.database import inicializar_db
import random

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Configuração de Pastas
os.makedirs("cogs", exist_ok=True)
os.makedirs("data", exist_ok=True)
os.makedirs("assets/sfx", exist_ok=True)

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

class ClutchBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        # Carrega extensões
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and filename != "__init__.py":
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"⚙️  Cog Carregado: {filename}")
                except Exception as e:
                    print(f"❌ Erro ao carregar {filename}: {e}")
        
        # Sincroniza Slash Commands
        try:
            await self.tree.sync()
            print("🌲 Slash Commands Sincronizados!")
        except Exception as e:
            print(f"❌ Erro no Sync: {e}")
        
        # Inicia loop de status
        self.status_loop.start()

    async def on_ready(self):
        print("---")
        print(f"✅ CLUTCH V2.5 ONLINE: {self.user.name}")
        await inicializar_db()
        print("---")

    @tasks.loop(seconds=60)
    async def status_loop(self):
        status_list = [
            discord.Activity(type=discord.ActivityType.listening, name="Spotify"),
            discord.Activity(type=discord.ActivityType.playing, name="RPG de Mesa"),
            discord.Activity(type=discord.ActivityType.watching, name="o servidor"),
            discord.Activity(type=discord.ActivityType.competing, name="pelo Top 1"),
            discord.Game(name="Clutch OS v2.5")
        ]
        await self.change_presence(activity=random.choice(status_list))

    @status_loop.before_loop
    async def before_status_loop(self):
        await self.wait_until_ready()

bot = ClutchBot()

if __name__ == "__main__":
    if TOKEN:
        try:
            bot.run(TOKEN)
        except KeyboardInterrupt:
            print("\n🛑 Bot desligado.")
    else:
        print("❌ ERRO: Token não encontrado no .env")
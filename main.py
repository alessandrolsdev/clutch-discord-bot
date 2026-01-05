import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Configuração Inicial
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Setup de Pastas
os.makedirs("cogs", exist_ok=True)
os.makedirs("temp", exist_ok=True)
os.makedirs("assets/sfx", exist_ok=True)

# Configuração do Bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True   # <--- NOVO: Permite ver membros para o ranking
intents.voice_states = True # <--- NOVO: Permite ver quem entra/sai de call
bot = commands.Bot(command_prefix="!", intents=intents)

# Função para carregar os Cogs (Departamentos)
async def load_extensions():
    # Lista de arquivos na pasta cogs
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and filename != "__init__.py":
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f"⚙️  Módulo carregado: {filename}")
            except Exception as e:
                print(f"❌ Erro ao carregar {filename}: {e}")

@bot.event
async def on_ready():
    print("---")
    print(f"✅ CLUTCH SYSTEM ONLINE: {bot.user.name}")
    print(f"🆔 ID: {bot.user.id}")
    print("---")

async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

if __name__ == "__main__":
    if TOKEN:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            # Se apertar Ctrl+C, ele cai aqui e só imprime a mensagem bonita
            print("\n🛑 Bot desligado manualmente pelo usuário.")
    else:
        print("❌ ERRO: Configure o .env")
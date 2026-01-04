import os
import asyncio
import discord
from discord.ext import commands
import google.generativeai as genai
import edge_tts
from dotenv import load_dotenv

# --- 1. CONFIGURAÇÕES E SETUP ---

# Carrega as variáveis do arquivo .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

# Cria as pastas necessárias automaticamente (para não dar erro)
os.makedirs("temp", exist_ok=True)
os.makedirs("assets/sfx", exist_ok=True)

# Configura a IA (Gemini)
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
else:
    print("⚠️ AVISO: Chave do Gemini não encontrada no .env. O modo IA não funcionará.")

# Configura o Bot do Discord
intents = discord.Intents.default()
intents.message_content = True # Permite ler o chat
bot = commands.Bot(command_prefix="!", intents=intents)

# --- 2. SISTEMA DE PERSONAS ---
PERSONAS = {
    "padrao": "Você é o Clutch, um assistente robótico útil e breve.",
    "coach": "Você é um Coach de crossfit intenso. GRITE, use gírias de academia, seja motivador e agressivo.",
    "tio": "Você é o Tio do Pavê brasileiro. Faça trocadilhos ruins com tudo o que disserem. Ria alto.",
    "sarcastico": "Você é uma IA cansada de humanos. Responda com ironia, sarcasmo e desdém."
}

# Estado inicial
estado = {
    "persona": "padrao",
    "voz": "pt-BR-AntonioNeural" # Voz masculina
}

# --- 3. MOTOR DE ÁUDIO (Engine) ---

async def gerar_tts(texto):
    """Converte texto em áudio MP3 usando Edge-TTS"""
    caminho_arquivo = "temp/fala.mp3"
    
    # Remove arquivo anterior para garantir que é novo
    if os.path.exists(caminho_arquivo):
        os.remove(caminho_arquivo)
    
    # Gera o áudio
    communicate = edge_tts.Communicate(texto, estado["voz"])
    await communicate.save(caminho_arquivo)
    return caminho_arquivo

async def tocar_audio(ctx, caminho_arquivo):
    """Toca o arquivo no canal de voz"""
    if not ctx.voice_client:
        await ctx.send("❌ Não estou conectado em um canal de voz.")
        return

    # Espera se já estiver falando algo
    while ctx.voice_client.is_playing():
        await asyncio.sleep(0.1)

    try:
        # Toca o áudio usando FFmpeg
        source = discord.FFmpegPCMAudio(source=caminho_arquivo, executable="ffmpeg")
        ctx.voice_client.play(source)
        
        # Espera terminar de tocar
        while ctx.voice_client.is_playing():
            await asyncio.sleep(0.1)
            
    except Exception as e:
        print(f"Erro ao tocar áudio: {e}")
        await ctx.send("⚠️ Erro interno de áudio.")

# --- 4. COMANDOS DO BOT ---

@bot.event
async def on_ready():
    print("---")
    print(f"✅ BOT ONLINE: {bot.user.name}")
    print(f"🆔 ID: {bot.user.id}")
    print("---")

@bot.command()
async def entrar(ctx):
    """Entra na call"""
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"🔊 Conectado em: **{channel.name}**")
    else:
        await ctx.send("❌ Entre em um canal de voz primeiro!")

@bot.command()
async def sair(ctx):
    """Sai da call"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Saindo...")

@bot.command()
async def diga(ctx, *, texto):
    """Fala o texto escrito"""
    await ctx.send(f"🗣️ **Falando:** {texto}")
    arquivo = await gerar_tts(texto)
    await tocar_audio(ctx, arquivo)

@bot.command(aliases=['c'])
async def clutch(ctx, *, pergunta):
    """Fala com a IA (Use !c ou !clutch)"""
    if not GEMINI_KEY:
        await ctx.send("❌ API do Gemini não configurada.")
        return

    # Prepara o prompt com a persona atual
    instrucao = PERSONAS.get(estado["persona"], PERSONAS["padrao"])
    prompt_final = f"{instrucao}\n\nO usuário disse: '{pergunta}'.\n(Responda de forma curta para ser falado, máximo 2 frases)."

    # Gera texto
    async with ctx.typing():
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt_final)
        resposta_texto = response.text

    await ctx.send(f"🤖 **({estado['persona']}):** {resposta_texto}")
    
    # Gera áudio e toca
    arquivo = await gerar_tts(resposta_texto)
    await tocar_audio(ctx, arquivo)

@bot.command()
async def incorporar(ctx, persona):
    """Muda a personalidade (padrao, coach, tio, sarcastico)"""
    if persona in PERSONAS:
        estado["persona"] = persona
        # Muda a voz se for o Tio (exemplo)
        if persona == "tio":
            estado["voz"] = "pt-BR-FranciscaNeural"
        else:
            estado["voz"] = "pt-BR-AntonioNeural"
            
        await ctx.send(f"🔄 Personalidade alterada para: **{persona.upper()}**")
    else:
        await ctx.send(f"❌ Persona inválida. Tente: {', '.join(PERSONAS.keys())}")

# --- 5. EXECUÇÃO ---
if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERRO CRÍTICO: Token não encontrado.")
        print("Verifique se o arquivo .env existe e tem a linha DISCORD_TOKEN=...")
    else:
        try:
            bot.run(TOKEN)
        except discord.errors.LoginFailure:
            print("\n❌ ERRO DE TOKEN: O Token no arquivo .env é inválido.")
            print("👉 Vá no Discord Developer Portal e gere um novo token.")
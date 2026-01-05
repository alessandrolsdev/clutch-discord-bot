import discord
from discord.ext import commands
import edge_tts
import os
import asyncio

class Audio(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voz_padrao = "pt-BR-AntonioNeural"

    # --- FUNÇÕES AUXILIARES ---
    async def gerar_tts(self, texto):
        """Gera o arquivo de áudio a partir do texto"""
        caminho = "temp/fala.mp3"
        # Remove arquivo anterior para evitar conflito
        if os.path.exists(caminho):
            os.remove(caminho)
            
        communicate = edge_tts.Communicate(texto, self.voz_padrao)
        await communicate.save(caminho)
        return caminho

    async def tocar_arquivo(self, ctx, caminho):
        """Função universal para tocar qualquer arquivo de áudio"""
        if not ctx.voice_client:
            await ctx.send("❌ Não estou conectado! Use `!entrar`.")
            return

        # Se já estiver tocando algo, espera terminar (fila simples)
        while ctx.voice_client.is_playing():
            await asyncio.sleep(0.1)

        try:
            # Toca o áudio
            # Se der erro de ffmpeg, lembre de colocar o caminho completo: executable=r"C:\ffmpeg\bin\ffmpeg.exe"
            source = discord.FFmpegPCMAudio(source=caminho, executable="ffmpeg")
            ctx.voice_client.play(source)
            
            # Espera o áudio acabar antes de liberar a função
            while ctx.voice_client.is_playing():
                await asyncio.sleep(0.1)
                
        except Exception as e:
            print(f"Erro Audio: {e}")
            await ctx.send("⚠️ Erro no áudio (Verifique se o FFmpeg está instalado).")

    # --- COMANDOS DE CONTROLE ---
    @commands.command()
    async def entrar(self, ctx):
        """Entra no canal de voz"""
        if ctx.author.voice:
            channel = ctx.author.voice.channel
            await channel.connect()
            await ctx.send(f"🔊 Plugado em: **{channel.name}**")
        else:
            await ctx.send("❌ Entre num canal de voz primeiro!")

    @commands.command()
    async def sair(self, ctx):
        """Sai do canal de voz"""
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("👋 Fui!")

    @commands.command()
    async def parar(self, ctx):
        """Para qualquer áudio imediatamente (Freio de Mão)"""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("🛑 **Parei!**")
        else:
            await ctx.send("😐 Não estou tocando nada no momento.")

    # --- COMANDOS DE FALA (TTS) ---
    @commands.command()
    async def diga(self, ctx, *, texto):
        """Fala o texto digitado"""
        await ctx.send(f"🗣️ **Falando:** {texto}")
        arquivo = await self.gerar_tts(texto)
        await self.tocar_arquivo(ctx, arquivo)

    # --- SOUNDBOARD (EFEITOS SONOROS) ---
    @commands.command()
    async def sfx(self, ctx, nome_som):
        """Toca um som da pasta assets/sfx"""
        caminho = f"assets/sfx/{nome_som}.mp3"
        
        if os.path.exists(caminho):
            await ctx.send(f"🎵 Play: **{nome_som}**")
            await self.tocar_arquivo(ctx, caminho)
        else:
            await ctx.send(f"❌ Som não encontrado: `{nome_som}`. Use `!sons` para ver a lista.")

    @commands.command()
    async def sons(self, ctx):
        """Lista os sons disponíveis"""
        try:
            arquivos = os.listdir("assets/sfx")
            # Filtra apenas arquivos .mp3
            lista = [f.replace(".mp3", "") for f in arquivos if f.endswith(".mp3")]
            
            if lista:
                msg = "**🎛️ Mesa de Som:** `" + "`, `".join(lista) + "`"
                await ctx.send(msg)
            else:
                await ctx.send("📂 A pasta de sons está vazia!")
        except Exception as e:
            await ctx.send(f"❌ Erro ao ler pasta: {e}")

    # --- POLTERGEIST (AUTO-REAÇÃO) ---
    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignora mensagens do próprio bot
        if message.author == self.bot.user:
            return

        conteudo = message.content.lower()
        
        # Só tenta tocar se o bot estiver conectado em um canal de voz
        if message.guild.voice_client and message.guild.voice_client.is_connected():
            
            # Gatilho: Risada
            if "kkkk" in conteudo or "hahaha" in conteudo:
                caminho = "assets/sfx/risada.mp3"
                if os.path.exists(caminho) and not message.guild.voice_client.is_playing():
                    source = discord.FFmpegPCMAudio(caminho)
                    message.guild.voice_client.play(source)

            # Gatilho: Tristeza (Opcional)
            elif "triste" in conteudo:
                caminho = "assets/sfx/sad.mp3"
                if os.path.exists(caminho) and not message.guild.voice_client.is_playing():
                    source = discord.FFmpegPCMAudio(caminho)
                    message.guild.voice_client.play(source)

# Função obrigatória para carregar o módulo
async def setup(bot):
    await bot.add_cog(Audio(bot))
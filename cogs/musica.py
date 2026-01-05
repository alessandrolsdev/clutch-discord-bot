import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os

class Musica(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Configurações do YT-DLP para baixar rápido e sem vídeo
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
            'outtmpl': 'temp/musica_%(id)s.%(ext)s', # Salva na pasta temp
            'quiet': True,
        }

    async def tocar_arquivo(self, ctx, caminho):
        """Reutiliza a lógica de tocar do módulo de áudio se possível, ou toca direto"""
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            
        source = discord.FFmpegPCMAudio(source=caminho, executable="ffmpeg")
        ctx.voice_client.play(source)

    @commands.command()
    async def play(self, ctx, *, busca):
        """Toca uma música do YouTube. Ex: !play Linkin Park Numb"""
        
        # 1. Garante que está no canal de voz
        if not ctx.author.voice:
            return await ctx.send("❌ Entre num canal de voz primeiro!")
        
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()

        await ctx.send(f"🔎 **Procurando:** `{busca}`... (Isso pode levar uns segundos)")

        # 2. Busca e baixa o áudio
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                # 'ytsearch1:' faz ele pegar o primeiro resultado da busca
                info = ydl.extract_info(f"ytsearch1:{busca}", download=True)
                
                if 'entries' in info:
                    info = info['entries'][0]
                    
                arquivo_mp3 = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")
                titulo = info['title']

            # 3. Toca
            await ctx.send(f"💿 **Tocando Agora:** `{titulo}`")
            await self.tocar_arquivo(ctx, arquivo_mp3)
            
        except Exception as e:
            await ctx.send(f"❌ Erro ao baixar/tocar: {e}")
            print(e)

    @commands.command()
    async def stop(self, ctx):
        """Para a música"""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("⏹️ Música parada.")

async def setup(bot):
    await bot.add_cog(Musica(bot))
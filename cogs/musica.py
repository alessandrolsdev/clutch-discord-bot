import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import os

# --- A CLASSE DOS BOTÕES (A Interface) ---
class MusicPlayerView(discord.ui.View):
    def __init__(self, voice_client):
        super().__init__(timeout=None) # Botões não expiram
        self.vc = voice_client

    @discord.ui.button(label="Pausar/Retomar", style=discord.ButtonStyle.primary, emoji="⏯️")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.vc.is_playing():
            self.vc.pause()
            await interaction.response.send_message("⏸️ Pausado!", ephemeral=True)
        elif self.vc.is_paused():
            self.vc.resume()
            await interaction.response.send_message("▶️ Retomado!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nada tocando.", ephemeral=True)

    @discord.ui.button(label="Parar", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.vc.is_playing() or self.vc.is_paused():
            self.vc.stop()
            await interaction.response.send_message("⏹️ Música parada e fila limpa.", ephemeral=True)
            self.stop() # Para a View também
        else:
            await interaction.response.send_message("❌ Já estou parado.", ephemeral=True)

class Musica(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
            'outtmpl': 'temp/musica_%(id)s.%(ext)s',
            'quiet': True,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'no_warnings': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web'], 'skip': ['hls', 'dash']}}
        }

    async def tocar_arquivo(self, interaction, caminho):
        """Função auxiliar para tocar"""
        vc = interaction.guild.voice_client
        
        if vc.is_playing():
            vc.stop()
            
        source = discord.FFmpegPCMAudio(source=caminho, executable="ffmpeg")
        vc.play(source)

    # --- COMANDO /PLAY (AGORA COM BOTÕES!) ---
    @app_commands.command(name="play", description="Toca uma música do YouTube")
    @app_commands.describe(busca="Nome da música ou Link")
    async def play(self, interaction: discord.Interaction, busca: str):
        # 1. Verifica canal de voz
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Entre num canal de voz primeiro!", ephemeral=True)
        
        # Conecta se necessário
        if not interaction.guild.voice_client:
            await interaction.user.voice.channel.connect()
        
        # 2. Avisa que está processando (Defer)
        # O YouTube demora, então precisamos avisar o Discord para "esperar" a resposta
        await interaction.response.defer()

        try:
            # 3. Baixa a música
            loop = asyncio.get_running_loop()
            # Roda o download em uma thread separada para não travar o bot
            data = await loop.run_in_executor(None, lambda: self._download(busca))
            
            arquivo = data['arquivo']
            titulo = data['titulo']
            thumb = data['thumbnail']

            # 4. Toca
            vc = interaction.guild.voice_client
            await self.tocar_arquivo(interaction, arquivo)

            # 5. Manda o Player Bonito com Botões
            embed = discord.Embed(title="💿 Tocando Agora", description=f"**{titulo}**", color=discord.Color.purple())
            embed.set_thumbnail(url=thumb)
            embed.set_footer(text=f"Pedido por {interaction.user.name}")
            
            view = MusicPlayerView(vc)
            await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            await interaction.followup.send(f"❌ Erro: {e}")

    def _download(self, busca):
        """Função síncrona de download (roda no executor)"""
        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{busca}", download=True)
            if 'entries' in info: info = info['entries'][0]
            arquivo = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")
            return {'arquivo': arquivo, 'titulo': info['title'], 'thumbnail': info['thumbnail']}

    @app_commands.command(name="stop", description="Para a música")
    async def stop_cmd(self, interaction: discord.Interaction):
        if interaction.guild.voice_client:
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("⏹️ Parado.")
        else:
            await interaction.response.send_message("😐 Não estou tocando nada.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Musica(bot))
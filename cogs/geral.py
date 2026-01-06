import discord
from discord import app_commands
from discord.ext import commands

# --- INTERFACE VISUAL (Dropdown) ---
class AjudaSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="🎵 Música & Áudio", description="Play, SFX, Voz", emoji="🎧"),
            discord.SelectOption(label="🧠 Inteligência & Caos", description="Chat, RPG, Vibe", emoji="🔮"),
            discord.SelectOption(label="👥 Social & Perfil", description="Níveis, Bio, Ranking", emoji="🏆"),
            discord.SelectOption(label="🛠️ Utilidades", description="Ping, Avatar", emoji="⚙️")
        ]
        super().__init__(placeholder="Escolha uma categoria...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        categoria = self.values[0]
        embed = discord.Embed(title=f"📘 Ajuda: {categoria}", color=0x00ff00)
        
        if "Música" in categoria:
            embed.description = (
                "`/play <busca>` - Toca música do YouTube (com botões!)\n"
                "`/stop` - Para a música\n"
                "`/sfx <nome>` - Toca efeito sonoro\n"
                "`/diga <texto>` - Fala em voz alta (TTS)"
            )
        elif "Inteligência" in categoria:
            embed.description = (
                "`/chat <msg>` - Conversa com memória\n"
                "`/persona <tipo>` - Muda a personalidade\n"
                "`/rpg <user>` - Ficha de personagem\n"
                "`/vibe` - Julga a aura da call\n"
                "`/shipp <A> <B>` - Teste de amor"
            )
        elif "Social" in categoria:
            embed.description = (
                "`/perfil` - Ver seu Card de Jogador\n"
                "`/bio <texto>` - Mudar sua biografia\n"
                "`/noticias` - Jornal do servidor (IA)"
            )
        else:
            embed.description = (
                "`/ping` - Latência do bot\n"
                "`/avatar <user>` - Roubar foto de perfil"
            )

        await interaction.response.edit_message(embed=embed, view=None)

class AjudaView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(AjudaSelect())

class Geral(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Verifica a conexão")
    async def ping(self, interaction: discord.Interaction):
        latencia = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"🏓 **Pong!** `{latencia}ms`")

    @app_commands.command(name="avatar", description="Zoom na foto de perfil")
    async def avatar(self, interaction: discord.Interaction, usuario: discord.Member = None):
        if not usuario: usuario = interaction.user
        embed = discord.Embed(title=f"📸 {usuario.name}", color=discord.Color.purple())
        embed.set_image(url=usuario.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ajuda", description="Painel de Controle do Bot")
    async def ajuda(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🤖 Central de Comando Clutch",
            description="Selecione uma categoria abaixo para ver os comandos disponíveis.",
            color=discord.Color.dark_theme()
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Clutch Systems V2.5")
        
        await interaction.response.send_message(embed=embed, view=AjudaView())

async def setup(bot):
    await bot.add_cog(Geral(bot))
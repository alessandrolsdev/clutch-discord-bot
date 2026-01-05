import discord
from discord.ext import commands
import random
from datetime import datetime

class Geral(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Remove o comando help padrão feio do Discord para usarmos o nosso
        self.bot.remove_command('help')

    @commands.command(name="ajuda", aliases=["help", "comandos"])
    async def ajuda(self, ctx):
        """Mostra o painel de controle do bot"""
        embed = discord.Embed(
            title="🤖 CLUTCH BOT - Painel de Controle",
            description="Aqui está tudo o que eu sei fazer (por enquanto):",
            color=0x00ff00, # Cor Verde Matrix
            timestamp=datetime.now()
        )
        embed.add_field(
            name="🏆 Funções Icônicas",
            value="`!rpg <@user>` - Gera ficha de RPG zueira\n`!vibe` - Julga a aura de alguém da call (Áudio)\n`!shipp <@A> <@B>` - Teste de casal caótico",
            inline=False
        )
        
        # Seção DJ e Áudio
        embed.add_field(
            name="🎧 DJ & Áudio",
            value="`!play <nome>` - Toca música do YouTube\n`!stop` - Para a música\n`!entrar` / `!sair` - Entra/Sai da call\n`!sfx <nome>` - Toca efeito sonoro\n`!sons` - Lista os efeitos disponíveis",
            inline=False
        )

        # Seção Inteligência
        embed.add_field(
            name="🧠 Inteligência (IA)",
            value="`!c <pergunta>` - Responde e fala em áudio\n`!incorporar <persona>` - Muda a personalidade\n`!batalha <A vs B>` - Narra uma luta",
            inline=False
        )

        # Seção Utilidades
        embed.add_field(
            name="🛠️ Utilidades",
            value="`!limpar <qtd>` - Apaga mensagens (Faxina)\n`!avatar <@user>` - Rouba a foto do amigo\n`!ping` - Vê se o bot está lagado",
            inline=False
        )
        
        embed.set_footer(text="Criado por Engenharia Clutch")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        await ctx.send(embed=embed)

    # --- COMANDOS JÁ EXISTENTES (Mantidos) ---
    
    @commands.command()
    async def ping(self, ctx):
        latencia = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 **Pong!** `{latencia}ms`")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def limpar(self, ctx, quantidade: int = 5):
        await ctx.channel.purge(limit=quantidade + 1)
        msg = await ctx.send(f"🧹 **Faxina:** {quantidade} msgs apagadas.")
        await discord.utils.sleep_until(discord.utils.utcnow() + discord.utils.timedelta(seconds=3))
        await msg.delete()

    @commands.command()
    async def avatar(self, ctx, usuario: discord.Member = None):
        if usuario is None: usuario = ctx.author
        embed = discord.Embed(title=f"📸 {usuario.name}", color=discord.Color.blue())
        embed.set_image(url=usuario.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command()
    async def escolha(self, ctx, *opcoes):
        if not opcoes: return await ctx.send("❌ Ex: `!escolha Pizza Burguer`")
        await ctx.send(f"🤔 Eu escolho... **{random.choice(opcoes)}**!")

async def setup(bot):
    await bot.add_cog(Geral(bot))
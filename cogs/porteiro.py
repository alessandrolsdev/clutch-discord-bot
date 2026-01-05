import discord
from discord.ext import commands
import os

class Porteiro(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        # Tenta achar o canal de sistema (onde o Discord avisa que alguém entrou)
        # Se não achar, procura um canal chamado "geral" ou "chat"
        canal = member.guild.system_channel
        if not canal:
            canal = discord.utils.get(member.guild.text_channels, name="geral")
        
        if canal:
            # Texto Bonito
            embed = discord.Embed(
                title=f"👋 Bem-vindo(a), {member.name}!",
                description=f"Seja muito bem-vindo ao servidor **{member.guild.name}**!\nNão esqueça de ler as regras.",
                color=discord.Color.green()
            )
            # Coloca a foto da pessoa no cartão
            embed.set_thumbnail(url=member.display_avatar.url)
            
            await canal.send(f"Olha quem chegou! {member.mention}", embed=embed)
            
            # (Opcional) Se quiser que o bot fale em áudio também:
            # audio_cog = self.bot.get_cog('Audio')
            # if audio_cog:
            #     texto_boas_vindas = f"Olá {member.name}, seja bem vindo ao servidor."
            #     arquivo = await audio_cog.gerar_tts(texto_boas_vindas)
            #     # O bot precisaria estar num canal de voz pra tocar, o que é difícil no join automático.

    @commands.command()
    async def testar_boasvindas(self, ctx):
        """Simula a entrada de alguém para testar o cartão"""
        # Finge que quem digitou o comando acabou de entrar
        await self.on_member_join(ctx.author)

async def setup(bot):
    await bot.add_cog(Porteiro(bot))
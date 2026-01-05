import discord
from discord.ext import commands
from datetime import datetime

class Vigia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Evento: Alguém apagou uma mensagem
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        # Ignora mensagens do próprio bot
        if message.author.bot:
            return

        # Monta a fofoca
        msg = (f"👀 **X-9 ONLINE:**\n"
               f"O usuário **{message.author.name}** apagou uma mensagem!\n"
               f"📄 Conteúdo: `{message.content}`")
        
        # Manda no mesmo canal onde foi apagado (ou poderia ser num canal de logs específico)
        await message.channel.send(msg)

    # Evento: Alguém editou uma mensagem
    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot:
            return
            
        # Só avisa se o texto mudou mesmo
        if before.content != after.content:
            msg = (f"✏️ **EDIÇÃO DETECTADA:**\n"
                   f"👤 **{before.author.name}** mudou de:\n"
                   f"`{before.content}`\n"
                   f"⬇️ para:\n"
                   f"`{after.content}`")
            await before.channel.send(msg)

async def setup(bot):
    await bot.add_cog(Vigia(bot))
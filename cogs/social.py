import discord
from discord import app_commands
from discord.ext import commands
from infra.database import get_conexao
from datetime import datetime
import time
import google.generativeai as genai
import os
import aiosqlite # <--- 1. ADICIONADO AQUI

MODEL_NAME = "gemini-2.5-flash"

class Social(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_sessions = {}
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key: genai.configure(api_key=self.api_key)

    # --- SQL HELPERS ---
    async def get_user_data(self, user_id, user_name):
        async with get_conexao() as db:
            db.row_factory = aiosqlite.Row # <--- 2. CORRIGIDO AQUI (Era discord.Row)
            
            async with db.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,)) as cursor:
                user = await cursor.fetchone()
            
            if not user:
                await db.execute("INSERT INTO usuarios (id, nome) VALUES (?, ?)", (user_id, user_name))
                await db.commit()
                async with db.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,)) as cursor:
                    user = await cursor.fetchone()
            
            async with db.execute("SELECT badge_name FROM conquistas WHERE user_id = ?", (user_id,)) as cursor:
                badges_rows = await cursor.fetchall()
                badges = [row[0] for row in badges_rows]
            
            return user, badges

    async def add_badge(self, channel, user_id, user_mention, badge_name):
        async with get_conexao() as db:
            cursor = await db.execute("SELECT 1 FROM conquistas WHERE user_id = ? AND badge_name = ?", (user_id, badge_name))
            if not await cursor.fetchone():
                hoje = datetime.now().strftime("%Y-%m-%d")
                await db.execute("INSERT INTO conquistas (user_id, badge_name, data_conquista) VALUES (?, ?, ?)", (user_id, badge_name, hoje))
                await db.commit()
                
                embed = discord.Embed(title="🏆 CONQUISTA!", description=f"Parabéns {user_mention}, você ganhou a medalha **{badge_name}**!", color=discord.Color.gold())
                if channel: await channel.send(embed=embed)

    async def add_badge_silent(self, user_id, badge_name):
        async with get_conexao() as db:
            cursor = await db.execute("SELECT 1 FROM conquistas WHERE user_id = ? AND badge_name = ?", (user_id, badge_name))
            if not await cursor.fetchone():
                hoje = datetime.now().strftime("%Y-%m-%d")
                await db.execute("INSERT INTO conquistas (user_id, badge_name, data_conquista) VALUES (?, ?, ?)", (user_id, badge_name, hoje))
                await db.commit()

    # --- LISTENERS ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return

        # A lógica aqui já chama get_user_data que abre a conexão corretamente
        user, badges = await self.get_user_data(message.author.id, message.author.name)
        
        novo_xp = user['xp'] + 10
        msg_count = user['msg_count'] + 1
        streak = user['streak']
        last_date = user['last_msg_date']
        hoje = datetime.now().strftime("%Y-%m-%d")

        if last_date != hoje:
            d1 = datetime.strptime(last_date, "%Y-%m-%d") if last_date else None
            d2 = datetime.strptime(hoje, "%Y-%m-%d")
            if d1 and (d2 - d1).days == 1: streak += 1
            elif d1 and (d2 - d1).days > 1: streak = 1
            else: streak = 1 if not d1 else streak
        
        level = user['level']
        if novo_xp >= (level * 100):
            level += 1
            novo_xp = 0
            await message.channel.send(f"🎉 **LEVEL UP!** {message.author.mention} subiu para o **Nível {level}**!")

        async with get_conexao() as db:
            await db.execute("UPDATE usuarios SET xp=?, msg_count=?, streak=?, last_msg_date=?, level=? WHERE id=?", 
                             (novo_xp, msg_count, streak, hoje, level, message.author.id))
            await db.commit()

        if msg_count >= 1: await self.add_badge(message.channel, message.author.id, message.author.mention, "👶 Novato")
        if streak >= 7: await self.add_badge(message.channel, message.author.id, message.author.mention, "🔥 On Fire")
        if level >= 10: await self.add_badge(message.channel, message.author.id, message.author.mention, "💎 VIP")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot: return
        
        if before.channel is None and after.channel is not None:
            self.voice_sessions[member.id] = time.time()
        
        elif before.channel is not None and after.channel is None:
            if member.id in self.voice_sessions:
                inicio = self.voice_sessions.pop(member.id)
                minutos = int((time.time() - inicio) / 60)
                
                if minutos > 0:
                    async with get_conexao() as db:
                        cursor = await db.execute("SELECT voice_minutes, xp FROM usuarios WHERE id = ?", (member.id,))
                        row = await cursor.fetchone()
                        if row:
                            novo_voice = row[0] + minutos
                            novo_xp = row[1] + (minutos * 5)
                            await db.execute("UPDATE usuarios SET voice_minutes = ?, xp = ? WHERE id = ?", (novo_voice, novo_xp, member.id))
                            await db.commit()
                            
                            if novo_voice >= 600: await self.add_badge_silent(member.id, "🎙️ Podcaster")

    # --- COMMANDS ---
    @app_commands.command(name="perfil", description="Ver Card de Jogador")
    async def perfil(self, interaction: discord.Interaction, usuario: discord.Member = None):
        if not usuario: usuario = interaction.user
        user, badges = await self.get_user_data(usuario.id, usuario.name)
        
        embed = discord.Embed(color=0xFFD700)
        embed.set_author(name=f"Perfil de {usuario.name}", icon_url=usuario.display_avatar.url)
        embed.set_thumbnail(url=usuario.display_avatar.url)
        
        embed.add_field(name="📜 Bio", value=f"_{user['bio']}_", inline=False)
        embed.add_field(name="🔥 Streak", value=f"**{user['streak']}** dias", inline=True)
        embed.add_field(name="⭐ Nível", value=f"**{user['level']}**", inline=True)
        embed.add_field(name="🎙️ Voz", value=f"**{user['voice_minutes']}** min", inline=True)
        
        badges_display = " ".join([f"`{b}`" for b in badges]) if badges else "Sem medalhas."
        embed.add_field(name="🏆 Conquistas", value=badges_display, inline=False)
        
        prox = user['level'] * 100
        prog = int((user['xp'] / prox) * 10)
        barra = "🟦" * prog + "⬛" * (10 - prog)
        embed.add_field(name=f"XP ({user['xp']}/{prox})", value=barra, inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="bio", description="Muda a bio do perfil")
    async def bio(self, interaction: discord.Interaction, texto: str):
        if len(texto) > 100: return await interaction.response.send_message("❌ Máximo 100 caracteres.", ephemeral=True)
        
        async with get_conexao() as db:
            await self.get_user_data(interaction.user.id, interaction.user.name)
            await db.execute("UPDATE usuarios SET bio = ? WHERE id = ?", (texto, interaction.user.id))
            await db.commit()
        await interaction.response.send_message(f"✅ Bio atualizada!")

    @app_commands.command(name="noticias", description="Jornal do Servidor (IA)")
    async def noticias(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        async with get_conexao() as db:
            async with db.execute("SELECT nome, level FROM usuarios ORDER BY xp DESC LIMIT 1") as cursor:
                top = await cursor.fetchone()
        
        if not top: return await interaction.followup.send("❌ Sem dados suficientes.")

        prompt = f"Escreva uma fofoca de jornal engraçada. Destaque: {top['nome']} é o Líder do servidor (Nível {top['level']}). Invente um boato."
        
        try:
            model = genai.GenerativeModel(MODEL_NAME)
            res = model.generate_content(prompt)
            embed = discord.Embed(title="📰 CLUTCH NEWS", description=res.text, color=discord.Color.orange())
            await interaction.followup.send(embed=embed)
        except: await interaction.followup.send("❌ IA Indisponível.")

async def setup(bot):
    await bot.add_cog(Social(bot))
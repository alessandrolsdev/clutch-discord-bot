import discord
from discord.ext import commands
import json
import os
from datetime import datetime
import time
import google.generativeai as genai

DB_FILE = "data/usuarios.json"

class Social(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_sessions = {}
        self.load_data()
        
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)

    def load_data(self):
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r") as f:
                self.users = json.load(f)
        else:
            self.users = {}
            self.save_data()

    def save_data(self):
        with open(DB_FILE, "w") as f:
            json.dump(self.users, f, indent=4)

    def get_user(self, user_id):
        uid = str(user_id)
        if uid not in self.users:
            self.users[uid] = {
                "xp": 0, "level": 1, "msg_count": 0,
                "voice_minutes": 0, "streak": 0,
                "last_msg_date": "", 
                "badges": [] # Lista de medalhas
            }
        return self.users[uid]

    # --- SISTEMA DE CONQUISTAS (NOVO) ---
    async def verificar_conquistas(self, ctx, user_data):
        """Verifica se o usuário desbloqueou algo novo"""
        badges_atuais = user_data.get("badges", [])
        novas_badges = []

        # 1. Badge: Novato (Primeira mensagem)
        if user_data["msg_count"] >= 1 and "👶 Novato" not in badges_atuais:
            novas_badges.append("👶 Novato")

        # 2. Badge: On Fire (Streak de 7 dias)
        if user_data["streak"] >= 7 and "🔥 On Fire" not in badges_atuais:
            novas_badges.append("🔥 On Fire")
            
        # 3. Badge: Podcaster (10 horas de voz = 600 min)
        if user_data["voice_minutes"] >= 600 and "🎙️ Podcaster" not in badges_atuais:
            novas_badges.append("🎙️ Podcaster")

        # 4. Badge: VIP (Nível 10)
        if user_data["level"] >= 10 and "💎 VIP" not in badges_atuais:
            novas_badges.append("💎 VIP")
            
        # 5. Badge: Coruja (Madrugada)
        hora_atual = datetime.now().hour
        if 3 <= hora_atual < 6 and "🌚 Coruja" not in badges_atuais:
            novas_badges.append("🌚 Coruja")

        # Se ganhou algo, salva e avisa
        if novas_badges:
            for b in novas_badges:
                user_data["badges"].append(b)
                # Aviso bonito no chat
                embed = discord.Embed(title="🏆 CONQUISTA DESBLOQUEADA!", description=f"Parabéns {ctx.author.mention}, você ganhou a medalha **{b}**!", color=discord.Color.gold())
                await ctx.send(embed=embed)
            self.save_data()

    # --- EVENTOS ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        user = self.get_user(message.author.id)
        
        user["xp"] += 10
        user["msg_count"] += 1
        
        # Streak Logic
        hoje = datetime.now().strftime("%Y-%m-%d")
        ultimo = user.get("last_msg_date")
        if ultimo != hoje:
            if ultimo:
                d1 = datetime.strptime(ultimo, "%Y-%m-%d")
                d2 = datetime.strptime(hoje, "%Y-%m-%d")
                if (d2 - d1).days == 1: user["streak"] += 1
                elif (d2 - d1).days > 1: user["streak"] = 1
            else: user["streak"] = 1
            user["last_msg_date"] = hoje

        # Level Logic
        prox = user["level"] * 100
        if user["xp"] >= prox:
            user["level"] += 1
            user["xp"] = 0
            await message.channel.send(f"🎉 **LEVEL UP!** {message.author.mention} ➡️ Nível {user['level']}!")

        # VERIFICA AS CONQUISTAS
        # Precisamos de um contexto fake ou passar o canal
        ctx = await self.bot.get_context(message)
        await self.verificar_conquistas(ctx, user)
            
        self.save_data()

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
                    user = self.get_user(member.id)
                    user["voice_minutes"] += minutos
                    user["xp"] += minutos * 5
                    self.save_data()

    # --- COMANDOS ---
    @commands.command(aliases=["p", "stats"])
    async def perfil(self, ctx, usuario: discord.Member = None):
        """Mostra o perfil com as medalhas"""
        if not usuario: usuario = ctx.author
        data = self.get_user(usuario.id)
        
        embed = discord.Embed(title=f"👤 Perfil de {usuario.name}", color=discord.Color.gold())
        embed.set_thumbnail(url=usuario.display_avatar.url)
        
        # Stats Principais
        stats = f"🔥 Streak: **{data['streak']} dias**\n🎙️ Voz: **{data['voice_minutes']} min**\n💬 Msgs: **{data['msg_count']}**"
        embed.add_field(name="Estatísticas", value=stats, inline=True)
        
        embed.add_field(name="⭐ Nível", value=f"**{data['level']}**", inline=True)
        
        # --- EXIBIÇÃO DE MEDALHAS ---
        badges = data.get("badges", [])
        if badges:
            badges_str = " ".join(badges) # Fica assim: 👶 Novato 🔥 On Fire
        else:
            badges_str = "Nenhuma... ainda!"
        
        embed.add_field(name="🏆 Sala de Troféus", value=badges_str, inline=False)
        
        # Barra de XP
        prox = data['level'] * 100
        prog = int((data['xp'] / prox) * 10)
        barra = "🟩" * prog + "⬜" * (10 - prog)
        embed.add_field(name=f"XP ({data['xp']}/{prox})", value=barra, inline=False)
        
        await ctx.send(embed=embed)

    @commands.command(aliases=["news"])
    async def noticias(self, ctx):
        """Gera a fofoca com IA"""
        if not self.users: return await ctx.send("❌ Sem dados!")
        
        top_xp = max(self.users.items(), key=lambda x: x[1]['xp'])
        member_xp = ctx.guild.get_member(int(top_xp[0]))
        nome_xp = member_xp.name if member_xp else "Desconhecido"
        
        prompt = (f"Escreva uma fofoca de jornal engraçada sobre o servidor. "
                  f"Destaque: O usuário '{nome_xp}' é o mais viciado (Nível {top_xp[1]['level']}). "
                  f"Invente um escândalo engraçado sobre isso.")
        
        async with ctx.typing():
            try:
                model = genai.GenerativeModel('gemini-pro')
                res = model.generate_content(prompt)
                embed = discord.Embed(title="🗞️ CLUTCH NEWS", description=res.text, color=discord.Color.orange())
                await ctx.send(embed=embed)
            except: await ctx.send("❌ A IA tirou folga.")

async def setup(bot):
    await bot.add_cog(Social(bot))
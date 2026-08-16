"""
COG: GERAL (UTILIDADES)
=======================

Comandos utilitários e painel de ajuda interativo.

Nota: o comando ``/ping`` vive no cog de monitoring. Ele existia aqui também,
e dois app commands com o mesmo nome fazem o discord.py levantar
``CommandAlreadyRegistered``, impedindo o carregamento de um dos cogs.
"""

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

CATEGORIAS = {
    "musica": {
        "label": "🎵 Música & Áudio",
        "description": "Play, SFX, Voz",
        "emoji": "🎧",
        "comandos": (
            "**Player**\n"
            "`/play <busca>` - Toca ou enfileira (aceita playlist)\n"
            "`/fila [pagina]` - Mostra a fila\n"
            "`/tocando` - Faixa atual com progresso\n"
            "`/pular` · `/pausar` · `/retomar` · `/stop`\n"
            "`/loop <modo>` - Repetir faixa ou fila\n"
            "`/embaralhar` · `/remover <n>` · `/mover <a> <b>`\n"
            "`/limparfila` · `/volume <0-150>`\n\n"
            "**Voz e efeitos**\n"
            "`/sfx <nome>` - Toca efeito sonoro\n"
            "`/diga <texto>` - Fala em voz alta (TTS)\n"
            "`/entrar` · `/sair` · `/parar`"
        ),
    },
    "ia": {
        "label": "🧠 Inteligência & Caos",
        "description": "Chat, RPG, Vibe",
        "emoji": "🔮",
        "comandos": (
            "`/chat <msg>` - Conversa com memória\n"
            "`/persona <tipo>` - Muda a personalidade\n"
            "`/esquecer` - Limpa sua conversa\n"
            "`/rpg <user>` - Ficha de personagem\n"
            "`/vibe` - Julga a aura da call\n"
            "`/shipp <A> <B>` - Teste de compatibilidade"
        ),
    },
    "social": {
        "label": "👥 Social & Perfil",
        "description": "Níveis, Bio, Ranking",
        "emoji": "🏆",
        "comandos": (
            "`/perfil` - Ver seu Card de Jogador\n"
            "`/bio <texto>` - Mudar sua biografia\n"
            "`/ranking` - Top 10 do servidor\n"
            "`/avisos` - Ver suas advertências\n"
            "`/noticias` - Jornal do servidor (IA)"
        ),
    },
    "moderacao": {
        "label": "🛡️ Moderação",
        "description": "Ban, castigo, avisos",
        "emoji": "🔨",
        "comandos": (
            "`/ban` · `/unban` · `/kick` - Remoção de membros\n"
            "`/castigo <min>` · `/descastigo` - Silenciar\n"
            "`/avisar` · `/avisos` · `/removeraviso` · `/limparavisos`\n"
            "`/limpar <n>` - Apaga mensagens em massa\n"
            "`/lento <seg>` - Modo lento do canal\n"
            "`/trancar` · `/destrancar` - Fecha/abre o canal\n"
            "_Requer as permissões correspondentes._"
        ),
    },
    "config": {
        "label": "⚙️ Configuração",
        "description": "Cargos, XP, logs",
        "emoji": "🔧",
        "comandos": (
            "**Cargos**\n"
            "`/nivelcargo definir <nivel> <cargo>` - Recompensa por nível\n"
            "`/nivelcargo listar` · `/nivelcargo remover`\n"
            "`/autorole <cargo>` - Cargo automático ao entrar\n"
            "`/painelcargos` - Painel com botões de cargo\n\n"
            "**Servidor**\n"
            "`/setlog <canal>` - Canal de logs\n"
            "`/boasvindas <canal>` - Canal de boas-vindas\n"
            "`/levelupcanal <canal>` - Onde anunciar level ups\n"
            "`/xpcanal [canal]` - Liga/desliga XP num canal\n"
            "`/xp <true|false>` - Liga/desliga a gamificação\n"
            "_Requer 'Gerenciar Servidor' ou 'Gerenciar Cargos'._"
        ),
    },
    "utils": {
        "label": "🛠️ Utilidades",
        "description": "Ping, Avatar, Status",
        "emoji": "⚙️",
        "comandos": (
            "`/ping` - Latência do bot\n"
            "`/avatar <user>` - Ver foto de perfil\n"
            "`/status` - Saúde do sistema\n"
            "`/uptime` - Tempo online\n"
            "`/ajuda` - Este painel"
        ),
    },
}


class AjudaSelect(discord.ui.Select):
    """Dropdown de categorias da ajuda."""

    def __init__(self):
        options = [
            discord.SelectOption(
                label=dados["label"],
                description=dados["description"],
                emoji=dados["emoji"],
                value=chave,
            )
            for chave, dados in CATEGORIAS.items()
        ]
        super().__init__(
            placeholder="Escolha uma categoria...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        """Mostra os comandos da categoria escolhida."""
        # O valor vem da chave do dicionário, não do rótulo traduzido —
        # antes a seleção era comparada por substring do label.
        dados = CATEGORIAS[self.values[0]]

        embed = discord.Embed(
            title=f"📘 Ajuda: {dados['label']}",
            description=dados["comandos"],
            color=0x00FF00,
        )
        await interaction.response.edit_message(embed=embed, view=None)


class AjudaView(discord.ui.View):
    """View com o dropdown de ajuda."""

    def __init__(self, autor_id: int):
        super().__init__(timeout=180)
        self.autor_id = autor_id
        self.add_item(AjudaSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Só quem pediu a ajuda navega no menu."""
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message(
                "❌ Use `/ajuda` para abrir o seu próprio painel.", ephemeral=True
            )
            return False
        return True


class Geral(commands.Cog):
    """Cog de comandos utilitários."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="avatar", description="Zoom na foto de perfil")
    @app_commands.describe(usuario="De quem? (padrão: você)")
    async def avatar(
        self,
        interaction: discord.Interaction,
        usuario: Optional[discord.Member] = None,
    ):
        """Exibe o avatar em tamanho grande."""
        alvo = usuario or interaction.user
        embed = discord.Embed(
            title=f"📸 {alvo.display_name}", color=discord.Color.purple()
        )
        embed.set_image(url=alvo.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ajuda", description="Painel de Controle do Bot")
    async def ajuda(self, interaction: discord.Interaction):
        """Abre o painel interativo de ajuda."""
        embed = discord.Embed(
            title="🤖 Central de Comando Clutch",
            description="Selecione uma categoria abaixo para ver os comandos disponíveis.",
            color=discord.Color.dark_theme(),
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Clutch Systems v3.0")

        await interaction.response.send_message(
            embed=embed, view=AjudaView(interaction.user.id)
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Geral(bot))

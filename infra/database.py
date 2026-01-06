"""
MÓDULO DE INFRAESTRUTURA - BANCO DE DADOS
=========================================

Gerencia o banco de dados SQLite do bot usando aiosqlite (async).

Esquema do Banco:
- usuarios: Perfis de usuários com XP, níveis, streak, bio
- conquistas: Badges/medalhas conquistadas pelos usuários
- guild_config: Configurações específicas de cada servidor

Todas as operações são assíncronas para não bloquear o bot.
"""

import aiosqlite
import os
from typing import Any

# Nome do arquivo do banco de dados
DB_NAME = "data/clutch.db"

# SQL para criar tabela de usuários
# Armazena dados de perfil e progresso de cada membro
CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,           -- ID do Discord do usuário
    nome TEXT,                         -- Nome de exibição
    xp INTEGER DEFAULT 0,              -- Experiência acumulada
    level INTEGER DEFAULT 1,           -- Nível atual (calculado a partir do XP)
    msg_count INTEGER DEFAULT 0,       -- Total de mensagens enviadas
    voice_minutes INTEGER DEFAULT 0,   -- Tempo total em canais de voz (minutos)
    streak INTEGER DEFAULT 0,          -- Dias consecutivos ativos
    last_msg_date TEXT,                -- Data da última mensagem (YYYY-MM-DD)
    bio TEXT DEFAULT 'Agente secreto do Clutch.'  -- Bio customizável
)
"""

# SQL para criar tabela de conquistas/badges
# Relaciona usuários com suas medalhas conquistadas
CREATE_BADGES_TABLE = """
CREATE TABLE IF NOT EXISTS conquistas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- ID único da conquista
    user_id INTEGER,                       -- ID do usuário que conquistou
    badge_name TEXT,                       -- Nome da medalha (ex: "👶 Novato")
    data_conquista TEXT,                   -- Data da conquista (YYYY-MM-DD)
    FOREIGN KEY(user_id) REFERENCES usuarios(id)
)
"""

# SQL para criar tabela de configurações por servidor
# Permite configurar comportamento do bot por guild
CREATE_CONFIG_TABLE = """
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER PRIMARY KEY,     -- ID do servidor Discord
    log_channel_id INTEGER            -- Canal para logs de moderação
)
"""


async def inicializar_db() -> None:
    """
    Inicializa o banco de dados criando todas as tabelas necessárias.

    - Cria a pasta /data se não existir
    - Cria as tabelas se não existirem (idempotente)
    - Executa no startup do bot (main.py)

    Raises:
        Exception: Se houver erro ao criar o banco
    """
    os.makedirs("data", exist_ok=True)

    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(CREATE_USERS_TABLE)
            await db.execute(CREATE_BADGES_TABLE)
            await db.execute(CREATE_CONFIG_TABLE)
            await db.commit()
        print("💾 Banco de Dados SQL inicializado com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao inicializar banco de dados: {e}")
        raise


def get_conexao() -> aiosqlite.Connection:
    """
    Retorna um gerenciador de contexto para conexão com o banco.

    Uso nos Cogs:
    ```python
    async with get_conexao() as db:
        cursor = await db.execute("SELECT * FROM usuarios")
        resultado = await cursor.fetchall()
    ```

    Returns:
        aiosqlite.Connection: Gerenciador de contexto da conexão

    Note:
        - Use sempre com 'async with' para garantir fechamento da conexão
        - Faça commit manual após operações de escrita: await db.commit()
    """
    return aiosqlite.connect(DB_NAME)

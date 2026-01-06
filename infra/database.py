import aiosqlite
import os

DB_NAME = "data/clutch.db"

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    nome TEXT,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    msg_count INTEGER DEFAULT 0,
    voice_minutes INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    last_msg_date TEXT,
    bio TEXT DEFAULT 'Agente secreto do Clutch.'
)
"""

CREATE_BADGES_TABLE = """
CREATE TABLE IF NOT EXISTS conquistas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    badge_name TEXT,
    data_conquista TEXT,
    FOREIGN KEY(user_id) REFERENCES usuarios(id)
)
"""

CREATE_CONFIG_TABLE = """
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER PRIMARY KEY,
    log_channel_id INTEGER
)
"""

async def inicializar_db():
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(CREATE_USERS_TABLE)
        await db.execute(CREATE_BADGES_TABLE)
        await db.execute(CREATE_CONFIG_TABLE)
        await db.commit()
    print("💾 Banco de Dados SQL inicializado com sucesso!")

# --- A CORREÇÃO ESTÁ AQUI ---
# Removemos o 'async' e o 'await' daqui. 
# Retornamos apenas o gerenciador de contexto para ser usado com 'async with' nos Cogs.
def get_conexao():
    return aiosqlite.connect(DB_NAME)
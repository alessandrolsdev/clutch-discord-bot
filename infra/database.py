"""
MÓDULO DE INFRAESTRUTURA - BANCO DE DADOS
=========================================

Gerencia o banco de dados SQLite do bot usando aiosqlite (async).

Esquema do Banco:
- usuarios: Perfis de usuários com XP, níveis, streak, bio
- conquistas: Badges/medalhas conquistadas pelos usuários
- guild_config: Configurações específicas de cada servidor

Todas as operações são assíncronas para não bloquear o bot.
Toda conexão obtida por ``get_conexao`` já vem com ``row_factory`` configurado,
então tanto ``row["nome"]`` quanto ``row[0]`` funcionam.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# Caminho do banco de dados (configurável via DB_PATH)
DB_NAME = settings.database.db_path

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
# UNIQUE(user_id, badge_name) impede medalha duplicada em corrida de eventos
CREATE_BADGES_TABLE = """
CREATE TABLE IF NOT EXISTS conquistas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- ID único da conquista
    user_id INTEGER NOT NULL,              -- ID do usuário que conquistou
    badge_name TEXT NOT NULL,              -- Nome da medalha (ex: "👶 Novato")
    data_conquista TEXT,                   -- Data da conquista (YYYY-MM-DD)
    UNIQUE(user_id, badge_name),
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

CREATE_BADGES_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_conquistas_user ON conquistas(user_id)"
)

# Índice do ranking (/perfil e /noticias ordenam por level+xp)
CREATE_RANKING_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_usuarios_ranking ON usuarios(level DESC, xp DESC)"
)


async def inicializar_db() -> None:
    """
    Inicializa o banco de dados criando todas as tabelas necessárias.

    - Cria a pasta do banco se não existir
    - Ativa WAL (melhor concorrência entre leituras e escritas)
    - Cria as tabelas e índices se não existirem (idempotente)

    Raises:
        Exception: Se houver erro ao criar o banco
    """
    Path(DB_NAME).parent.mkdir(parents=True, exist_ok=True)

    try:
        async with aiosqlite.connect(
            DB_NAME, timeout=settings.database.timeout
        ) as db:
            if settings.database.enable_wal:
                await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(CREATE_USERS_TABLE)
            await db.execute(CREATE_BADGES_TABLE)
            await db.execute(CREATE_CONFIG_TABLE)
            await db.execute(CREATE_BADGES_INDEX)
            await db.execute(CREATE_RANKING_INDEX)
            await db.commit()
        logger.info("💾 Banco de dados inicializado em %s", DB_NAME)
    except Exception as e:
        logger.critical("❌ Erro ao inicializar banco de dados: %s", e, exc_info=True)
        raise


@asynccontextmanager
async def get_conexao() -> AsyncIterator[aiosqlite.Connection]:
    """
    Abre uma conexão com o banco já configurada.

    A conexão vem com ``row_factory = aiosqlite.Row`` (acesso por nome de
    coluna) e ``foreign_keys`` ligado.

    Uso nos Cogs:
    ```python
    async with get_conexao() as db:
        async with db.execute("SELECT * FROM usuarios") as cursor:
            resultado = await cursor.fetchall()
    ```

    Note:
        Faça commit manual após operações de escrita: ``await db.commit()``
    """
    async with aiosqlite.connect(DB_NAME, timeout=settings.database.timeout) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def get_log_channel_id(guild_id: int) -> "int | None":
    """
    Retorna o canal de logs configurado para um servidor.

    Args:
        guild_id: ID do servidor Discord

    Returns:
        ID do canal de log, ou None se não configurado
    """
    async with get_conexao() as db:
        async with db.execute(
            "SELECT log_channel_id FROM guild_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

    return row["log_channel_id"] if row else None


async def set_log_channel_id(guild_id: int, channel_id: "int | None") -> None:
    """
    Define (ou limpa) o canal de logs de moderação de um servidor.

    Args:
        guild_id: ID do servidor Discord
        channel_id: ID do canal, ou None para desativar os logs
    """
    async with get_conexao() as db:
        await db.execute(
            """
            INSERT INTO guild_config (guild_id, log_channel_id) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET log_channel_id = excluded.log_channel_id
            """,
            (guild_id, channel_id),
        )
        await db.commit()

"""
MÓDULO DE INFRAESTRUTURA - BANCO DE DADOS
=========================================

Gerencia o banco de dados SQLite do bot usando aiosqlite (async).

Esquema do Banco:
- usuarios: Perfis de usuários com XP, níveis, streak, bio
- conquistas: Badges/medalhas conquistadas pelos usuários
- guild_config: Configurações por servidor (logs, boas-vindas, XP, autorole)
- level_roles: Cargos concedidos automaticamente ao atingir um nível
- warns: Histórico de advertências de moderação
- xp_ignored_channels: Canais que não concedem XP
- button_roles / button_role_items: Painéis de auto-atribuição de cargos
- automod_palavras / automod_isentos: Filtro de palavras e isenções do automod

Todas as operações são assíncronas para não bloquear o bot.
Toda conexão obtida por ``get_conexao`` já vem com ``row_factory`` configurado,
então tanto ``row["nome"]`` quanto ``row[0]`` funcionam.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

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

# Configurações por servidor
CREATE_CONFIG_TABLE = """
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER PRIMARY KEY,          -- ID do servidor Discord
    log_channel_id INTEGER                 -- Canal para logs de moderação
)
"""

# Colunas adicionadas depois da criação original da tabela.
# São aplicadas via ALTER TABLE para não quebrar bancos já existentes.
GUILD_CONFIG_COLUNAS: Dict[str, str] = {
    "levelup_channel_id": "INTEGER",  # Canal de anúncio de level up (NULL = canal da msg)
    "levelup_enabled": "INTEGER NOT NULL DEFAULT 1",
    "xp_enabled": "INTEGER NOT NULL DEFAULT 1",
    "welcome_channel_id": "INTEGER",  # Canal de boas-vindas
    "welcome_enabled": "INTEGER NOT NULL DEFAULT 1",
    "autorole_id": "INTEGER",  # Cargo concedido ao entrar no servidor
    "dj_role_id": "INTEGER",  # Cargo que pode controlar a música dos outros
    "music_max_queue": "INTEGER NOT NULL DEFAULT 100",
    # --- Automod (0 desliga a regra correspondente) ---
    "automod_ativo": "INTEGER NOT NULL DEFAULT 0",
    "automod_spam_mensagens": "INTEGER NOT NULL DEFAULT 5",
    "automod_spam_janela": "INTEGER NOT NULL DEFAULT 5",
    "automod_flood": "INTEGER NOT NULL DEFAULT 3",
    "automod_convites": "INTEGER NOT NULL DEFAULT 1",
    "automod_links": "INTEGER NOT NULL DEFAULT 0",
    "automod_mencoes": "INTEGER NOT NULL DEFAULT 5",
    "automod_caps": "INTEGER NOT NULL DEFAULT 70",
    "automod_castigo_minutos": "INTEGER NOT NULL DEFAULT 10",
    "automod_avisos_castigo": "INTEGER NOT NULL DEFAULT 3",
}

# Cargos automáticos por nível
CREATE_LEVEL_ROLES_TABLE = """
CREATE TABLE IF NOT EXISTS level_roles (
    guild_id INTEGER NOT NULL,
    level INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, level)
)
"""

# Advertências de moderação
CREATE_WARNS_TABLE = """
CREATE TABLE IF NOT EXISTS warns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL
)
"""

# Canais que não concedem XP
CREATE_XP_IGNORED_TABLE = """
CREATE TABLE IF NOT EXISTS xp_ignored_channels (
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, channel_id)
)
"""

# Palavras proibidas por servidor
CREATE_AUTOMOD_PALAVRAS_TABLE = """
CREATE TABLE IF NOT EXISTS automod_palavras (
    guild_id INTEGER NOT NULL,
    palavra TEXT NOT NULL,
    PRIMARY KEY (guild_id, palavra)
)
"""

# Canais e cargos isentos do automod
CREATE_AUTOMOD_ISENTOS_TABLE = """
CREATE TABLE IF NOT EXISTS automod_isentos (
    guild_id INTEGER NOT NULL,
    alvo_id INTEGER NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('canal', 'cargo')),
    PRIMARY KEY (guild_id, alvo_id, tipo)
)
"""

# Painéis de auto-atribuição de cargo (botões persistentes)
CREATE_BUTTON_ROLES_TABLE = """
CREATE TABLE IF NOT EXISTS button_roles (
    message_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
)
"""

CREATE_BUTTON_ROLE_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS button_role_items (
    message_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    emoji TEXT,
    PRIMARY KEY (message_id, role_id),
    FOREIGN KEY (message_id) REFERENCES button_roles(message_id) ON DELETE CASCADE
)
"""

INDICES = (
    "CREATE INDEX IF NOT EXISTS idx_conquistas_user ON conquistas(user_id)",
    # Ranking (/perfil, /ranking, /noticias ordenam por level+xp)
    "CREATE INDEX IF NOT EXISTS idx_usuarios_ranking ON usuarios(level DESC, xp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_warns_user ON warns(guild_id, user_id)",
    "CREATE INDEX IF NOT EXISTS idx_level_roles_guild ON level_roles(guild_id, level)",
    "CREATE INDEX IF NOT EXISTS idx_automod_isentos ON automod_isentos(guild_id)",
)

TABELAS = (
    CREATE_USERS_TABLE,
    CREATE_BADGES_TABLE,
    CREATE_CONFIG_TABLE,
    CREATE_LEVEL_ROLES_TABLE,
    CREATE_WARNS_TABLE,
    CREATE_XP_IGNORED_TABLE,
    CREATE_BUTTON_ROLES_TABLE,
    CREATE_BUTTON_ROLE_ITEMS_TABLE,
    CREATE_AUTOMOD_PALAVRAS_TABLE,
    CREATE_AUTOMOD_ISENTOS_TABLE,
)


async def _migrar_guild_config(db: aiosqlite.Connection) -> None:
    """
    Adiciona as colunas novas de ``guild_config`` em bancos antigos.

    SQLite não tem ``ADD COLUMN IF NOT EXISTS``, então consultamos o schema
    atual e aplicamos só o que falta. Rodar duas vezes é seguro.
    """
    async with db.execute("PRAGMA table_info(guild_config)") as cursor:
        existentes = {linha[1] for linha in await cursor.fetchall()}

    for coluna, tipo in GUILD_CONFIG_COLUNAS.items():
        if coluna not in existentes:
            await db.execute(f"ALTER TABLE guild_config ADD COLUMN {coluna} {tipo}")
            logger.info("Migração: coluna guild_config.%s adicionada", coluna)


async def inicializar_db() -> None:
    """
    Inicializa o banco de dados criando todas as tabelas necessárias.

    - Cria a pasta do banco se não existir
    - Ativa WAL (melhor concorrência entre leituras e escritas)
    - Cria tabelas e índices se não existirem (idempotente)
    - Aplica migrações de colunas novas

    Raises:
        Exception: Se houver erro ao criar o banco
    """
    Path(DB_NAME).parent.mkdir(parents=True, exist_ok=True)

    try:
        async with aiosqlite.connect(DB_NAME, timeout=settings.database.timeout) as db:
            if settings.database.enable_wal:
                await db.execute("PRAGMA journal_mode=WAL")

            for tabela in TABELAS:
                await db.execute(tabela)

            await _migrar_guild_config(db)

            for indice in INDICES:
                await db.execute(indice)

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


# ---------------------------------------------------------------------------
# CONFIGURAÇÃO POR SERVIDOR
# ---------------------------------------------------------------------------


async def carregar_guild_config(guild_id: int) -> Dict[str, Any]:
    """
    Lê a configuração de um servidor.

    Args:
        guild_id: ID do servidor Discord

    Returns:
        dict com as colunas de guild_config (vazio se nunca configurado)
    """
    async with get_conexao() as db:
        async with db.execute(
            "SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

    return dict(row) if row else {}


async def salvar_guild_config(guild_id: int, **campos: Any) -> None:
    """
    Grava campos de configuração de um servidor (upsert).

    Args:
        guild_id: ID do servidor Discord
        **campos: Colunas de guild_config a atualizar

    Raises:
        ValueError: Se algum campo não existir no schema
    """
    validos = set(GUILD_CONFIG_COLUNAS) | {"log_channel_id"}
    desconhecidos = set(campos) - validos
    if desconhecidos:
        raise ValueError(f"Campos inválidos em guild_config: {sorted(desconhecidos)}")

    if not campos:
        return

    colunas = list(campos)
    # Interpolação restrita aos nomes já validados contra o schema
    placeholders = ", ".join("?" for _ in colunas)
    atualizacoes = ", ".join(f"{c} = excluded.{c}" for c in colunas)

    async with get_conexao() as db:
        await db.execute(
            f"INSERT INTO guild_config (guild_id, {', '.join(colunas)}) "
            f"VALUES (?, {placeholders}) "
            f"ON CONFLICT(guild_id) DO UPDATE SET {atualizacoes}",
            (guild_id, *(campos[c] for c in colunas)),
        )
        await db.commit()


async def get_log_channel_id(guild_id: int) -> Optional[int]:
    """
    Retorna o canal de logs configurado para um servidor.

    Mantido por compatibilidade; prefira ``utils.guild_config.obter`` nos
    caminhos quentes, que usa cache em memória.
    """
    config = await carregar_guild_config(guild_id)
    return config.get("log_channel_id")


async def set_log_channel_id(guild_id: int, channel_id: Optional[int]) -> None:
    """Define (ou limpa) o canal de logs de moderação de um servidor."""
    await salvar_guild_config(guild_id, log_channel_id=channel_id)


# ---------------------------------------------------------------------------
# CANAIS IGNORADOS PARA XP
# ---------------------------------------------------------------------------


async def listar_canais_ignorados(guild_id: int) -> List[int]:
    """Retorna os canais que não concedem XP no servidor."""
    async with get_conexao() as db:
        async with db.execute(
            "SELECT channel_id FROM xp_ignored_channels WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            return [linha["channel_id"] for linha in await cursor.fetchall()]


async def alternar_canal_ignorado(guild_id: int, channel_id: int) -> bool:
    """
    Liga/desliga o ganho de XP em um canal.

    Returns:
        True se o canal passou a ser ignorado, False se voltou a dar XP
    """
    async with get_conexao() as db:
        cursor = await db.execute(
            "DELETE FROM xp_ignored_channels WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )
        if cursor.rowcount:
            await db.commit()
            return False

        await db.execute(
            "INSERT INTO xp_ignored_channels (guild_id, channel_id) VALUES (?, ?)",
            (guild_id, channel_id),
        )
        await db.commit()
        return True


# ---------------------------------------------------------------------------
# CARGOS POR NÍVEL
# ---------------------------------------------------------------------------


async def listar_level_roles(guild_id: int) -> List[Dict[str, int]]:
    """Retorna os cargos por nível do servidor, do menor nível para o maior."""
    async with get_conexao() as db:
        async with db.execute(
            "SELECT level, role_id FROM level_roles WHERE guild_id = ? ORDER BY level",
            (guild_id,),
        ) as cursor:
            return [dict(linha) for linha in await cursor.fetchall()]


async def definir_level_role(guild_id: int, level: int, role_id: int) -> None:
    """Associa um cargo a um nível (substitui o cargo anterior daquele nível)."""
    async with get_conexao() as db:
        await db.execute(
            "INSERT INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, level) DO UPDATE SET role_id = excluded.role_id",
            (guild_id, level, role_id),
        )
        await db.commit()


async def remover_level_role(guild_id: int, level: int) -> bool:
    """Remove a recompensa de um nível. Retorna True se havia algo para remover."""
    async with get_conexao() as db:
        cursor = await db.execute(
            "DELETE FROM level_roles WHERE guild_id = ? AND level = ?",
            (guild_id, level),
        )
        await db.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# ADVERTÊNCIAS (WARNS)
# ---------------------------------------------------------------------------


async def adicionar_warn(
    guild_id: int, user_id: int, moderator_id: int, reason: Optional[str]
) -> int:
    """
    Registra uma advertência.

    Returns:
        Total de advertências que o usuário passou a ter
    """
    agora = datetime.now(timezone.utc).isoformat()

    async with get_conexao() as db:
        await db.execute(
            "INSERT INTO warns (guild_id, user_id, moderator_id, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, reason, agora),
        )
        await db.commit()

        async with db.execute(
            "SELECT COUNT(*) AS total FROM warns WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cursor:
            linha = await cursor.fetchone()

    return linha["total"]


async def listar_warns(guild_id: int, user_id: int) -> List[Dict[str, Any]]:
    """Retorna as advertências de um usuário, da mais recente para a mais antiga."""
    async with get_conexao() as db:
        async with db.execute(
            "SELECT id, moderator_id, reason, created_at FROM warns "
            "WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
            (guild_id, user_id),
        ) as cursor:
            return [dict(linha) for linha in await cursor.fetchall()]


async def remover_warn(guild_id: int, warn_id: int) -> bool:
    """Remove uma advertência pelo ID. Retorna True se existia."""
    async with get_conexao() as db:
        cursor = await db.execute(
            "DELETE FROM warns WHERE guild_id = ? AND id = ?", (guild_id, warn_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def limpar_warns(guild_id: int, user_id: int) -> int:
    """Remove todas as advertências de um usuário. Retorna quantas foram apagadas."""
    async with get_conexao() as db:
        cursor = await db.execute(
            "DELETE FROM warns WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        )
        await db.commit()
        return cursor.rowcount


# ---------------------------------------------------------------------------
# PAINÉIS DE CARGO POR BOTÃO
# ---------------------------------------------------------------------------


async def salvar_painel_cargos(
    message_id: int,
    guild_id: int,
    channel_id: int,
    itens: List[Dict[str, Any]],
) -> None:
    """
    Persiste um painel de auto-atribuição de cargos.

    Args:
        message_id: Mensagem que contém os botões
        guild_id: Servidor
        channel_id: Canal da mensagem
        itens: Lista de {"role_id", "label", "emoji"}
    """
    agora = datetime.now(timezone.utc).isoformat()

    async with get_conexao() as db:
        await db.execute(
            "INSERT OR REPLACE INTO button_roles (message_id, guild_id, channel_id, created_at) "
            "VALUES (?, ?, ?, ?)",
            (message_id, guild_id, channel_id, agora),
        )
        await db.execute("DELETE FROM button_role_items WHERE message_id = ?", (message_id,))
        await db.executemany(
            "INSERT INTO button_role_items (message_id, role_id, label, emoji) "
            "VALUES (?, ?, ?, ?)",
            [
                (message_id, item["role_id"], item["label"], item.get("emoji"))
                for item in itens
            ],
        )
        await db.commit()


async def listar_paineis_cargos() -> List[Dict[str, Any]]:
    """
    Retorna todos os painéis de cargo salvos, com seus itens.

    Usado no startup para reconstruir as views persistentes.
    """
    async with get_conexao() as db:
        async with db.execute(
            "SELECT message_id, guild_id, channel_id FROM button_roles"
        ) as cursor:
            paineis = [dict(linha) for linha in await cursor.fetchall()]

        for painel in paineis:
            async with db.execute(
                "SELECT role_id, label, emoji FROM button_role_items WHERE message_id = ?",
                (painel["message_id"],),
            ) as cursor:
                painel["itens"] = [dict(linha) for linha in await cursor.fetchall()]

    return paineis


async def remover_painel_cargos(message_id: int) -> bool:
    """Apaga um painel de cargos. Retorna True se existia."""
    async with get_conexao() as db:
        await db.execute("DELETE FROM button_role_items WHERE message_id = ?", (message_id,))
        cursor = await db.execute(
            "DELETE FROM button_roles WHERE message_id = ?", (message_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# AUTOMOD
# ---------------------------------------------------------------------------


async def listar_palavras_proibidas(guild_id: int) -> List[str]:
    """Retorna as palavras proibidas do servidor."""
    async with get_conexao() as db:
        async with db.execute(
            "SELECT palavra FROM automod_palavras WHERE guild_id = ? ORDER BY palavra",
            (guild_id,),
        ) as cursor:
            return [linha["palavra"] for linha in await cursor.fetchall()]


async def adicionar_palavra_proibida(guild_id: int, palavra: str) -> bool:
    """
    Adiciona uma palavra à lista.

    Returns:
        False se a palavra já estava na lista
    """
    palavra = palavra.strip().casefold()
    if not palavra:
        return False

    async with get_conexao() as db:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO automod_palavras (guild_id, palavra) VALUES (?, ?)",
            (guild_id, palavra),
        )
        await db.commit()
        return cursor.rowcount > 0


async def remover_palavra_proibida(guild_id: int, palavra: str) -> bool:
    """Remove uma palavra da lista. Retorna True se existia."""
    async with get_conexao() as db:
        cursor = await db.execute(
            "DELETE FROM automod_palavras WHERE guild_id = ? AND palavra = ?",
            (guild_id, palavra.strip().casefold()),
        )
        await db.commit()
        return cursor.rowcount > 0


async def listar_isentos(guild_id: int) -> Dict[str, List[int]]:
    """
    Retorna canais e cargos isentos do automod.

    Returns:
        {"canal": [...], "cargo": [...]}
    """
    resultado: Dict[str, List[int]] = {"canal": [], "cargo": []}

    async with get_conexao() as db:
        async with db.execute(
            "SELECT alvo_id, tipo FROM automod_isentos WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            for linha in await cursor.fetchall():
                resultado[linha["tipo"]].append(linha["alvo_id"])

    return resultado


async def alternar_isento(guild_id: int, alvo_id: int, tipo: str) -> bool:
    """
    Liga/desliga a isenção de um canal ou cargo.

    Args:
        guild_id: Servidor
        alvo_id: ID do canal ou cargo
        tipo: "canal" ou "cargo"

    Returns:
        True se passou a ser isento, False se deixou de ser
    """
    if tipo not in ("canal", "cargo"):
        raise ValueError(f"tipo inválido: {tipo}")

    async with get_conexao() as db:
        cursor = await db.execute(
            "DELETE FROM automod_isentos WHERE guild_id = ? AND alvo_id = ? AND tipo = ?",
            (guild_id, alvo_id, tipo),
        )
        if cursor.rowcount:
            await db.commit()
            return False

        await db.execute(
            "INSERT INTO automod_isentos (guild_id, alvo_id, tipo) VALUES (?, ?, ?)",
            (guild_id, alvo_id, tipo),
        )
        await db.commit()
        return True

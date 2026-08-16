"""
CLUTCH BOT - CACHE DE CONFIGURAÇÃO POR SERVIDOR
===============================================

Cache em memória da tabela ``guild_config``.

Por que existe:
Os listeners rodam em caminho quente — ``on_message`` dispara em toda mensagem
do servidor, ``on_message_delete`` em toda exclusão. Ler a configuração direto
do SQLite nesses pontos significa uma query por evento; num servidor ativo
isso vira milhares de idas ao banco por minuto para ler dados que quase nunca
mudam.

O cache é preenchido sob demanda e invalidado explicitamente por quem grava
(os comandos de configuração), então nunca serve valor obsoleto.
"""

from dataclasses import dataclass
from typing import Dict, Optional

from infra.database import (
    carregar_guild_config,
    listar_canais_ignorados,
    salvar_guild_config,
)
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class GuildConfig:
    """Configuração efetiva de um servidor (com os padrões já aplicados)."""

    guild_id: int
    log_channel_id: Optional[int] = None
    levelup_channel_id: Optional[int] = None
    levelup_enabled: bool = True
    xp_enabled: bool = True
    welcome_channel_id: Optional[int] = None
    welcome_enabled: bool = True
    autorole_id: Optional[int] = None
    dj_role_id: Optional[int] = None
    music_max_queue: int = 100
    xp_ignored_channels: frozenset = frozenset()

    def da_xp_no_canal(self, channel_id: int) -> bool:
        """True se mensagens neste canal devem conceder XP."""
        return self.xp_enabled and channel_id not in self.xp_ignored_channels


def _para_bool(valor, padrao: bool = True) -> bool:
    """Converte o inteiro do SQLite em bool, preservando o padrão se for NULL."""
    if valor is None:
        return padrao
    return bool(valor)


class GuildConfigCache:
    """Cache de configurações por servidor, invalidado na escrita."""

    def __init__(self) -> None:
        self._cache: Dict[int, GuildConfig] = {}

    async def obter(self, guild_id: int) -> GuildConfig:
        """
        Retorna a configuração do servidor, consultando o banco só na 1ª vez.

        Args:
            guild_id: ID do servidor Discord

        Returns:
            GuildConfig com os padrões aplicados
        """
        cacheado = self._cache.get(guild_id)
        if cacheado is not None:
            return cacheado

        dados = await carregar_guild_config(guild_id)
        ignorados = await listar_canais_ignorados(guild_id)

        config = GuildConfig(
            guild_id=guild_id,
            log_channel_id=dados.get("log_channel_id"),
            levelup_channel_id=dados.get("levelup_channel_id"),
            levelup_enabled=_para_bool(dados.get("levelup_enabled")),
            xp_enabled=_para_bool(dados.get("xp_enabled")),
            welcome_channel_id=dados.get("welcome_channel_id"),
            welcome_enabled=_para_bool(dados.get("welcome_enabled")),
            autorole_id=dados.get("autorole_id"),
            dj_role_id=dados.get("dj_role_id"),
            music_max_queue=dados.get("music_max_queue") or 100,
            xp_ignored_channels=frozenset(ignorados),
        )

        self._cache[guild_id] = config
        return config

    async def atualizar(self, guild_id: int, **campos) -> GuildConfig:
        """
        Grava campos no banco e invalida o cache do servidor.

        Args:
            guild_id: ID do servidor Discord
            **campos: Colunas de guild_config a atualizar

        Returns:
            A configuração recarregada
        """
        await salvar_guild_config(guild_id, **campos)
        self.invalidar(guild_id)
        return await self.obter(guild_id)

    def invalidar(self, guild_id: int) -> None:
        """Descarta a entrada de cache de um servidor."""
        self._cache.pop(guild_id, None)

    def limpar(self) -> None:
        """Esvazia o cache inteiro (usado em testes e no reload de cogs)."""
        self._cache.clear()

    @property
    def tamanho(self) -> int:
        """Quantidade de servidores em cache (exposto em /status)."""
        return len(self._cache)


# Instância compartilhada por todos os cogs
guild_config = GuildConfigCache()

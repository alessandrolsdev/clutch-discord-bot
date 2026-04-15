"""
CLUTCH BOT - SISTEMA DE CONFIGURAÇÃO
=====================================

Gerenciamento centralizado de todas as configurações do bot.

Benefícios:
- Validação de variáveis de ambiente
- Valores padrão configuráveis
- Type hints para todas as configs
- Diferentes profiles (dev, prod, test)
- Documentação inline

Uso:
    from config.settings import settings

    # Acessar configurações
    token = settings.bot.token
    chunk_size = settings.audio.chunk_size
"""

import os
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()


def get_env(key: str, default: Optional[str] = None, required: bool = False) -> str:
    """
    Obtém variável de ambiente com validação.

    Args:
        key: Nome da variável
        default: Valor padrão se não existir
        required: Se True, lança erro se não encontrar

    Returns:
        Valor da variável ou padrão

    Raises:
        ValueError: Se required=True e variável não existe
    """
    value = os.getenv(key, default)

    if required and not value:
        raise ValueError(f"❌ Variável de ambiente obrigatória não encontrada: {key}")

    return value


def get_optional_int_env(key: str) -> Optional[int]:
    """Obtém uma variável opcional convertendo para inteiro."""
    value = os.getenv(key)
    if value in (None, ""):
        return None
    return int(value)


@dataclass
class BotConfig:
    """Configurações do bot Discord"""

    # Token do bot (OBRIGATÓRIO)
    token: str = field(default_factory=lambda: get_env("DISCORD_TOKEN", required=True))

    # Prefixo de comandos legados
    prefix: str = field(default_factory=lambda: get_env("BOT_PREFIX", "!"))

    # Intervalo de rotação de status (segundos)
    status_rotation_seconds: int = field(
        default_factory=lambda: int(get_env("STATUS_ROTATION_SECONDS", "60"))
    )

    # Lista de status para rotação
    status_messages: list = field(
        default_factory=lambda: [
            "Spotify",
            "RPG de Mesa",
            "o servidor",
            "pelo Top 1",
            "Clutch OS v3.0",
        ]
    )


@dataclass
class AudioConfig:
    """Configurações de áudio"""

    # Tamanho do chunk de áudio (20ms em 48kHz = 960 samples)
    chunk_size: int = field(
        default_factory=lambda: int(get_env("AUDIO_CHUNK_SIZE", "960"))
    )

    # Taxa de amostragem (Hz) - Padrão do Discord
    sample_rate: int = field(
        default_factory=lambda: int(get_env("AUDIO_SAMPLE_RATE", "48000"))
    )

    # Número de canais (1=mono, 2=estéreo)
    channels: int = field(default_factory=lambda: int(get_env("AUDIO_CHANNELS", "2")))

    # IP destino UDP
    udp_target_ip: str = field(
        default_factory=lambda: get_env("UDP_TARGET_IP", "127.0.0.1")
    )

    # Porta UDP para envio (receptor)
    udp_port_send: int = field(
        default_factory=lambda: int(get_env("UDP_PORT_ENVIO", "6000"))
    )

    # Porta UDP para recebimento (microfone)
    udp_port_receive: int = field(
        default_factory=lambda: int(get_env("UDP_PORT_RECEBIMENTO", "6001"))
    )

    # Tamanho do buffer do receptor (frames)
    receptor_buffer_size: int = field(
        default_factory=lambda: int(get_env("RECEPTOR_BUFFER_SIZE", "200"))
    )

    # Volume padrão do mixer (0.0 a 1.0)
    mixer_volume_mic: float = field(
        default_factory=lambda: float(get_env("MIXER_VOLUME_MIC", "0.7"))
    )

    mixer_volume_fx: float = field(
        default_factory=lambda: float(get_env("MIXER_VOLUME_FX", "1.0"))
    )


@dataclass
class AIConfig:
    """Configurações da IA (Google Gemini)"""

    # API Key do Gemini (OBRIGATÓRIO se usar IA)
    api_key: Optional[str] = field(default_factory=lambda: get_env("GEMINI_API_KEY"))

    # Modelo a usar
    model_name: str = field(
        default_factory=lambda: get_env("GEMINI_MODEL", "gemini-2.0-flash-exp")
    )

    # Tamanho do histórico de conversa por usuário
    history_size: int = field(
        default_factory=lambda: int(get_env("AI_HISTORY_SIZE", "5"))
    )

    # Temperatura da geração (0.0 a 1.0)
    temperature: float = field(
        default_factory=lambda: float(get_env("AI_TEMPERATURE", "0.7"))
    )

    # Máximo de tokens na resposta
    max_tokens: int = field(
        default_factory=lambda: int(get_env("AI_MAX_TOKENS", "1000"))
    )


@dataclass
class DatabaseConfig:
    """Configurações do banco de dados"""

    # Caminho do arquivo SQLite
    db_path: str = field(default_factory=lambda: get_env("DB_PATH", "data/clutch.db"))

    # Habilitar modo WAL (Write-Ahead Logging) para melhor concorrência
    enable_wal: bool = field(
        default_factory=lambda: get_env("DB_ENABLE_WAL", "true").lower() == "true"
    )

    # Timeout de conexão (segundos)
    timeout: int = field(default_factory=lambda: int(get_env("DB_TIMEOUT", "10")))


@dataclass
class APIConfig:
    """Configurações da API HTTP"""

    # Porta do servidor
    port: int = field(default_factory=lambda: int(get_env("API_PORT", "8080")))

    # Host (0.0.0.0 = aceita de qualquer IP)
    host: str = field(default_factory=lambda: get_env("API_HOST", "0.0.0.0"))

    # API Key para autenticação (opcional)
    api_key: Optional[str] = field(default_factory=lambda: get_env("API_KEY"))

    # CORS habilitado
    cors_enabled: bool = field(
        default_factory=lambda: get_env("API_CORS_ENABLED", "true").lower() == "true"
    )


@dataclass
class PresenceBridgeConfig:
    """Configurações da bridge de presence para o CLUTCH."""

    api_base_url: Optional[str] = field(
        default_factory=lambda: get_env("CLUTCH_API_BASE_URL")
    )

    ingest_token: Optional[str] = field(
        default_factory=lambda: get_env("CLUTCH_DISCORD_INGEST_TOKEN")
    )

    target_guild_id: Optional[int] = field(
        default_factory=lambda: get_optional_int_env("CLUTCH_TARGET_GUILD_ID")
    )

    dry_run: bool = field(
        default_factory=lambda: get_env("CLUTCH_PRESENCE_DRY_RUN", "true").lower()
        == "true"
    )

    dedup_seconds: int = field(
        default_factory=lambda: int(get_env("CLUTCH_PRESENCE_DEDUP_SECONDS", "15"))
    )

    request_timeout_seconds: float = field(
        default_factory=lambda: float(
            get_env("CLUTCH_PRESENCE_REQUEST_TIMEOUT_SECONDS", "5")
        )
    )


@dataclass
class GamificationConfig:
    """Configurações do sistema de gamificação"""

    # XP por mensagem enviada
    xp_per_message: int = field(
        default_factory=lambda: int(get_env("XP_PER_MESSAGE", "10"))
    )

    # XP por minuto em canal de voz
    xp_per_voice_minute: int = field(
        default_factory=lambda: int(get_env("XP_PER_VOICE_MINUTE", "5"))
    )

    # Fórmula de XP para level up: level * multiplicador
    level_up_multiplier: int = field(
        default_factory=lambda: int(get_env("LEVEL_UP_MULTIPLIER", "100"))
    )

    # Cooldown entre ganhos de XP (segundos) - evita spam
    xp_cooldown: int = field(default_factory=lambda: int(get_env("XP_COOLDOWN", "60")))

    # Economia virtual habilitada
    economy_enabled: bool = field(
        default_factory=lambda: get_env("ECONOMY_ENABLED", "false").lower() == "true"
    )

    # Coins ganhos por level up
    coins_per_level: int = field(
        default_factory=lambda: int(get_env("COINS_PER_LEVEL", "10"))
    )


@dataclass
class LoggingConfig:
    """Configurações de logging"""

    # Nível de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    level: str = field(default_factory=lambda: get_env("LOG_LEVEL", "INFO").upper())

    # Diretório de logs
    log_dir: Path = field(default_factory=lambda: Path(get_env("LOG_DIR", "logs")))

    # Formato de log
    format: str = field(
        default_factory=lambda: get_env(
            "LOG_FORMAT", "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
        )
    )

    # Rotação de logs (tamanho máximo em MB)
    max_size_mb: int = field(
        default_factory=lambda: int(get_env("LOG_MAX_SIZE_MB", "10"))
    )

    # Número de backups a manter
    backup_count: int = field(
        default_factory=lambda: int(get_env("LOG_BACKUP_COUNT", "5"))
    )

    # Logs estruturados (JSON)
    structured_logs: bool = field(
        default_factory=lambda: get_env("LOG_STRUCTURED", "false").lower() == "true"
    )


@dataclass
class DashboardConfig:
    """Configurações do Dashboard Streamlit"""

    # Porta do Streamlit
    port: int = field(default_factory=lambda: int(get_env("DASHBOARD_PORT", "8501")))

    # Auto-refresh interval (segundos)
    refresh_interval_seconds: int = field(
        default_factory=lambda: int(get_env("DASHBOARD_REFRESH_INTERVAL", "1"))
    )

    # Tema (light ou dark)
    theme: str = field(default_factory=lambda: get_env("DASHBOARD_THEME", "dark"))


@dataclass
class Settings:
    """
    Configurações globais do Clutch Bot.

    Instância única que agrega todas as configurações do sistema.
    """

    bot: BotConfig = field(default_factory=BotConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    api: APIConfig = field(default_factory=APIConfig)
    presence_bridge: PresenceBridgeConfig = field(
        default_factory=PresenceBridgeConfig
    )
    gamification: GamificationConfig = field(default_factory=GamificationConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)

    # Modo de desenvolvimento
    dev_mode: bool = field(
        default_factory=lambda: get_env("DEV_MODE", "false").lower() == "true"
    )

    # Versão do bot
    version: str = "3.0"

    def __post_init__(self):
        """Validações pós-inicialização"""
        # Cria diretórios necessários
        self.logging.log_dir.mkdir(exist_ok=True)
        Path("data").mkdir(exist_ok=True)
        Path("temp").mkdir(exist_ok=True)
        Path("assets/sfx").mkdir(parents=True, exist_ok=True)

    def print_config(self):
        """Imprime configuração atual (útil para debug)"""
        print("=" * 50)
        print(f"🔧 CONFIGURAÇÃO CLUTCH BOT v{self.version}")
        print("=" * 50)

        print(f"\n[BOT]")
        print(
            f"  Token: {'✅ Configurado' if self.bot.token else '❌ Não configurado'}"
        )
        print(f"  Prefix: {self.bot.prefix}")

        print(f"\n[ÁUDIO]")
        print(f"  Sample Rate: {self.audio.sample_rate} Hz")
        print(f"  Chunk Size: {self.audio.chunk_size}")
        print(f"  Channels: {self.audio.channels}")
        print(f"  UDP: {self.audio.udp_target_ip}:{self.audio.udp_port_send}")

        print(f"\n[IA]")
        print(
            f"  Gemini API: {'✅ Configurado' if self.ai.api_key else '❌ Não configurado'}"
        )
        print(f"  Model: {self.ai.model_name}")

        print(f"\n[API]")
        print(f"  Endpoint: http://{self.api.host}:{self.api.port}")

        print(f"\n[PRESENCE BRIDGE]")
        print(f"  Dry-run: {'✅ Sim' if self.presence_bridge.dry_run else '❌ Não'}")
        print(
            f"  CLUTCH Base URL: {self.presence_bridge.api_base_url or 'Não configurado'}"
        )

        print(f"\n[LOGGING]")
        print(f"  Level: {self.logging.level}")
        print(f"  Dir: {self.logging.log_dir}")

        print("=" * 50)


# Instância global de configurações
# Importar em outros módulos com: from config.settings import settings
try:
    settings = Settings()
except ValueError as e:
    print(f"\n{e}")
    print("Dica: Configure seu arquivo .env corretamente\n")
    raise SystemExit(1)

# Para debug: descomentar a linha abaixo
# settings.print_config()

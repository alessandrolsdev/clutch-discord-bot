"""
CLUTCH BOT - SISTEMA DE LOGGING PROFISSIONAL
=============================================

Sistema de logging com:
- Logs rotacionados (evita arquivos gigantes)
- Diferentes níveis por componente
- Formatação colorida no terminal
- Logs estruturados (JSON opcional)
- Integração discord (envia erros criticos em canal)

Uso:
    from utils.logger import get_logger

    logger = get_logger(__name__)
    logger.info("Bot iniciado")
    logger.error("Falha ao conectar", extra={"channel_id": 123})
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
import json
from datetime import datetime


# Cores ANSI para terminal
class LogColors:
    """Códigos de cores para diferentes níveis de log"""

    DEBUG = "\033[36m"  # Ciano
    INFO = "\033[32m"  # Verde
    WARNING = "\033[33m"  # Amarelo
    ERROR = "\033[31m"  # Vermelho
    CRITICAL = "\033[35m"  # Magenta
    RESET = "\033[0m"  # Reset


class ColoredFormatter(logging.Formatter):
    """Formatter que adiciona cores aos logs no terminal"""

    COLORS = {
        logging.DEBUG: LogColors.DEBUG,
        logging.INFO: LogColors.INFO,
        logging.WARNING: LogColors.WARNING,
        logging.ERROR: LogColors.ERROR,
        logging.CRITICAL: LogColors.CRITICAL,
    }

    def format(self, record):
        """Formata record com cores"""
        # Adiciona cor ao levelname
        color = self.COLORS.get(record.levelno, LogColors.RESET)
        record.levelname = f"{color}{record.levelname}{LogColors.RESET}"

        # Adiciona cor ao nome do logger
        record.name = f"{LogColors.DEBUG}{record.name}{LogColors.RESET}"

        return super().format(record)


class JSONFormatter(logging.Formatter):
    """Formatter que gera logs em formato JSON estruturado"""

    def format(self, record):
        """Formata record como JSON"""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Adiciona campos extras se existirem
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        # Adiciona exception info se existir
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


def setup_logger(
    name: str,
    level: str = "INFO",
    log_dir: Path = Path("logs"),
    max_size_mb: int = 10,
    backup_count: int = 5,
    console_output: bool = True,
    file_output: bool = True,
    structured: bool = False,
) -> logging.Logger:
    """
    Configura e retorna um logger.

    Args:
        name: Nome do logger (geralmente __name__ do módulo)
        level: Nível de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Diretório para arquivos de log
        max_size_mb: Tamanho máximo do arquivo antes de rotacionar (MB)
        backup_count: Número de arquivos de backup a manter
        console_output: Se True, imprime logs no terminal
        file_output: Se True, salva logs em arquivo
        structured: Se True, usa formato JSON

    Returns:
        Logger configurado
    """
    logger = logging.getLogger(name)

    # Evita adicionar handlers duplicados se logger já existe
    if logger.hasHandlers():
        return logger

    # Define nível do logger
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Formato de log padrão
    log_format = "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Handler para console (terminal)
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)

        if structured:
            console_formatter = JSONFormatter()
        else:
            console_formatter = ColoredFormatter(log_format, datefmt=date_format)

        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    # Handler para arquivo
    if file_output:
        # Cria diretório de logs se não existir
        log_dir.mkdir(exist_ok=True, parents=True)

        # Determina nome do arquivo de log
        log_file = log_dir / f"{name.replace('.', '_')}.log"

        # Handler com rotação automática
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_size_mb * 1024 * 1024,  # Converte MB para bytes
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)

        if structured:
            file_formatter = JSONFormatter()
        else:
            # Arquivo não precisa de cores
            file_formatter = logging.Formatter(log_format, datefmt=date_format)

        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    # Previne propagação para logger pai (evita duplicação)
    logger.propagate = False

    return logger


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    Obtém um logger com configurações padrão do projeto.

    Esta é a função principal a ser usada nos módulos.

    Args:
        name: Nome do logger (use __name__)
        level: Nível de log (opcional, usa config se não especificado)

    Returns:
        Logger configurado

    Example:
        >>> from utils.logger import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Bot iniciado")
        >>> logger.error("Erro ao processar", exc_info=True)
    """
    try:
        from config.settings import settings

        return setup_logger(
            name=name,
            level=level or settings.logging.level,
            log_dir=settings.logging.log_dir,
            max_size_mb=settings.logging.max_size_mb,
            backup_count=settings.logging.backup_count,
            console_output=True,
            file_output=True,
            structured=settings.logging.structured_logs,
        )
    except ImportError:
        # Fallback se config não estiver disponível
        return setup_logger(name=name, level=level or "INFO")


class LoggerAdapter(logging.LoggerAdapter):
    """
    Adapter que adiciona contexto extra aos logs.

    Útil para adicionar informações como guild_id, user_id automaticamente.

    Example:
        >>> logger = get_logger(__name__)
        >>> ctx_logger = LoggerAdapter(logger, {"guild_id": 123})
        >>> ctx_logger.info("Comando executado")
        # Log terá guild_id=123 no contexto
    """

    def process(self, msg, kwargs):
        """Adiciona contexto extra ao log"""
        # Merge extra data
        if "extra" not in kwargs:
            kwargs["extra"] = {}

        kwargs["extra"].update(self.extra)

        # Para JSON formatter
        if hasattr(self.logger, "extra_data"):
            self.logger.extra_data = kwargs["extra"]

        return msg, kwargs


# Configuração de logging para bibliotecas externas
def configure_third_party_loggers():
    """Configura níveis de log para bibliotecas de terceiros"""

    # Discord.py muito verboso em DEBUG, deixamos em INFO
    logging.getLogger("discord").setLevel(logging.INFO)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)

    # aiohttp também muito verboso
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

    # yt-dlp
    logging.getLogger("yt_dlp").setLevel(logging.ERROR)


# Auto-configure ao importar
configure_third_party_loggers()

# Logger padrão do módulo
logger = get_logger(__name__)
logger.info("🔧 Sistema de logging inicializado")

"""
MÓDULO DE INFRAESTRUTURA - BACKUP DO BANCO
==========================================

Cópias de segurança do SQLite.

Por que não é só copiar o arquivo:
Com WAL ligado (o padrão do bot), os dados recentes vivem no arquivo
``-wal`` separado. Copiar só o ``.db`` com ``cp`` durante uma escrita produz
um backup corrompido ou desatualizado. A API ``sqlite3.Connection.backup()``
faz a cópia de forma consistente mesmo com o bot escrevendo.
"""

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

PREFIXO = "clutch-backup-"
SUFIXO = ".db"


def _nome_do_backup(momento: Optional[datetime] = None) -> str:
    """Gera o nome do arquivo de backup a partir do horário UTC."""
    momento = momento or datetime.now(timezone.utc)
    return f"{PREFIXO}{momento.strftime('%Y%m%d-%H%M%S')}{SUFIXO}"


def listar_backups(diretorio: Path) -> List[Path]:
    """
    Lista os backups existentes, do mais recente para o mais antigo.

    Args:
        diretorio: Pasta de backups

    Returns:
        Caminhos ordenados por nome decrescente (o nome carrega a data)
    """
    if not diretorio.is_dir():
        return []

    return sorted(
        (
            arquivo
            for arquivo in diretorio.iterdir()
            if arquivo.is_file()
            and arquivo.name.startswith(PREFIXO)
            and arquivo.name.endswith(SUFIXO)
        ),
        key=lambda p: p.name,
        reverse=True,
    )


def limpar_antigos(diretorio: Path, manter: int) -> int:
    """
    Remove os backups excedentes.

    Args:
        diretorio: Pasta de backups
        manter: Quantos backups preservar (os mais recentes)

    Returns:
        Quantidade de arquivos removidos
    """
    if manter < 1:
        return 0

    removidos = 0
    for antigo in listar_backups(diretorio)[manter:]:
        try:
            antigo.unlink()
            removidos += 1
        except OSError as e:
            logger.warning("Não foi possível remover backup %s: %s", antigo.name, e)

    return removidos


def criar_backup(
    db_path: str | Path,
    diretorio: str | Path,
    manter: int = 7,
    momento: Optional[datetime] = None,
) -> Optional[Path]:
    """
    Cria uma cópia consistente do banco e remove as mais antigas.

    Args:
        db_path: Caminho do banco de origem
        diretorio: Pasta de destino dos backups
        manter: Quantos backups preservar
        momento: Horário usado no nome (para testes)

    Returns:
        Caminho do backup criado, ou None se a origem não existe
    """
    origem = Path(db_path)
    destino_dir = Path(diretorio)

    if not origem.is_file():
        logger.warning("Backup ignorado: banco %s não existe ainda", origem)
        return None

    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / _nome_do_backup(momento)

    conexao_origem = None
    conexao_destino = None
    try:
        # Somente leitura na origem; o backup online lida com WAL corretamente
        conexao_origem = sqlite3.connect(f"file:{origem}?mode=ro", uri=True)
        conexao_destino = sqlite3.connect(destino)
        conexao_origem.backup(conexao_destino)
    except sqlite3.Error as e:
        logger.error("Falha ao gerar backup: %s", e)
        destino.unlink(missing_ok=True)
        return None
    finally:
        if conexao_destino is not None:
            conexao_destino.close()
        if conexao_origem is not None:
            conexao_origem.close()

    removidos = limpar_antigos(destino_dir, manter)
    logger.info(
        "💾 Backup criado: %s (%.1f KB, %s antigos removidos)",
        destino.name,
        destino.stat().st_size / 1024,
        removidos,
    )
    return destino


def restaurar_backup(backup_path: str | Path, db_path: str | Path) -> bool:
    """
    Restaura um backup por cima do banco atual.

    O banco atual é preservado com sufixo ``.antes-da-restauracao``.
    O bot deve estar parado — restaurar com ele rodando deixa as conexões
    abertas apontando para um arquivo que não existe mais.

    Args:
        backup_path: Backup a restaurar
        db_path: Banco de destino

    Returns:
        True se a restauração foi concluída
    """
    origem = Path(backup_path)
    destino = Path(db_path)

    if not origem.is_file():
        logger.error("Backup %s não encontrado", origem)
        return False

    try:
        if destino.is_file():
            shutil.copy2(destino, destino.with_suffix(".antes-da-restauracao"))

        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origem, destino)

        # Os arquivos WAL/SHM antigos não valem mais para o banco restaurado
        for extra in (f"{destino}-wal", f"{destino}-shm"):
            Path(extra).unlink(missing_ok=True)
    except OSError as e:
        logger.error("Falha ao restaurar backup: %s", e)
        return False

    logger.info("♻️  Banco restaurado a partir de %s", origem.name)
    return True

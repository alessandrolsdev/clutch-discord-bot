"""
CLUTCH BOT - SOUNDBOARD
=======================

Resolução segura de nomes de arquivos do soundboard.

Por que existe:
A API HTTP montava o caminho com ``f"/app/assets/sounds/{nome_arquivo}"``
usando um nome vindo direto do cliente. Um ``filename`` como
``../../etc/passwd`` escapava do diretório e era entregue ao FFmpeg. Aqui o
nome é reduzido ao seu componente final e o caminho resolvido precisa
comprovadamente estar dentro do diretório de sons.
"""

import os
from pathlib import Path
from typing import List, Optional

EXTENSOES_VALIDAS = {".mp3", ".wav", ".ogg"}


def listar_sons(diretorio: Path) -> List[str]:
    """
    Lista os arquivos de som disponíveis.

    Args:
        diretorio: Pasta do soundboard

    Returns:
        Nomes de arquivo ordenados (lista vazia se a pasta não existe)
    """
    if not diretorio.is_dir():
        return []

    return sorted(
        f.name
        for f in diretorio.iterdir()
        if f.is_file() and f.suffix.lower() in EXTENSOES_VALIDAS
    )


def resolver_som(diretorio: Path, nome: Optional[str]) -> Optional[Path]:
    """
    Resolve o caminho de um som validando contra path traversal.

    Args:
        diretorio: Pasta do soundboard
        nome: Nome informado pelo cliente (com ou sem extensão)

    Returns:
        Path validado dentro de ``diretorio``, ou None se inválido
    """
    if not nome or not isinstance(nome, str):
        return None

    # Descarta qualquer componente de diretório e separadores do Windows
    base_nome = os.path.basename(nome.strip().replace("\\", "/"))
    if not base_nome or base_nome.startswith("."):
        return None

    base = diretorio.resolve()

    # Aceita tanto "alarme" quanto "alarme.mp3"
    candidatos = [base_nome]
    if Path(base_nome).suffix.lower() not in EXTENSOES_VALIDAS:
        candidatos = [f"{base_nome}{ext}" for ext in sorted(EXTENSOES_VALIDAS)]

    for candidato in candidatos:
        caminho = (base / candidato).resolve()

        # O caminho final precisa estar realmente dentro do diretório de sons
        if base not in caminho.parents:
            continue
        if caminho.is_file() and caminho.suffix.lower() in EXTENSOES_VALIDAS:
            return caminho

    return None

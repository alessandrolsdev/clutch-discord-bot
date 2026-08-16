"""
CLUTCH BOT - FILA DE MÚSICA
===========================

Estruturas puras da fila de reprodução (sem dependência do discord.py), para
poderem ser testadas isoladamente.

Modos de repetição:
- OFF: toca a fila até acabar
- TRACK: repete a faixa atual indefinidamente
- QUEUE: ao terminar, a faixa volta para o fim da fila
"""

import random
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, List, Optional


class LoopMode(str, Enum):
    """Modo de repetição da fila."""

    OFF = "off"
    TRACK = "track"
    QUEUE = "queue"

    @property
    def rotulo(self) -> str:
        """Nome amigável para exibir no player."""
        return {
            LoopMode.OFF: "➡️ Desligado",
            LoopMode.TRACK: "🔂 Faixa",
            LoopMode.QUEUE: "🔁 Fila",
        }[self]


@dataclass
class Track:
    """Uma faixa na fila."""

    title: str
    stream_url: str
    webpage_url: Optional[str] = None
    duration: Optional[int] = None
    thumbnail: Optional[str] = None
    requester_id: Optional[int] = None
    uploader: Optional[str] = None

    @property
    def duracao_formatada(self) -> str:
        """Duração como MM:SS ou HH:MM:SS (── para lives/desconhecido)."""
        return formatar_duracao(self.duration)

    def __str__(self) -> str:
        return self.title


def formatar_duracao(segundos: Optional[int]) -> str:
    """
    Formata segundos como MM:SS ou HH:MM:SS.

    Args:
        segundos: Duração (None para lives ou desconhecido)

    Returns:
        String formatada, ou "──:──" se não houver duração
    """
    if not segundos or segundos < 0:
        return "──:──"

    segundos = int(segundos)
    horas, resto = divmod(segundos, 3600)
    minutos, segs = divmod(resto, 60)

    if horas:
        return f"{horas}:{minutos:02d}:{segs:02d}"
    return f"{minutos}:{segs:02d}"


def barra_progresso(atual: int, total: Optional[int], tamanho: int = 20) -> str:
    """
    Desenha uma barra de progresso textual.

    Args:
        atual: Segundos decorridos
        total: Duração total (None = indeterminado)
        tamanho: Número de caracteres da barra

    Returns:
        Barra no formato ▬▬▬🔘▬▬▬
    """
    if not total or total <= 0:
        return "🔴 AO VIVO"

    proporcao = min(max(atual / total, 0.0), 1.0)
    posicao = min(int(proporcao * tamanho), tamanho - 1)
    return "▬" * posicao + "🔘" + "▬" * (tamanho - posicao - 1)


@dataclass
class Fila:
    """
    Fila de reprodução de um servidor.

    Attributes:
        itens: Faixas aguardando reprodução
        atual: Faixa tocando agora
        loop: Modo de repetição
        historico: Últimas faixas tocadas (para /voltar)
        limite: Máximo de faixas na fila
    """

    itens: Deque[Track] = field(default_factory=deque)
    atual: Optional[Track] = None
    loop: LoopMode = LoopMode.OFF
    historico: Deque[Track] = field(default_factory=lambda: deque(maxlen=20))
    limite: int = 100

    def __len__(self) -> int:
        return len(self.itens)

    @property
    def cheia(self) -> bool:
        """True se a fila atingiu o limite configurado."""
        return len(self.itens) >= self.limite

    @property
    def duracao_total(self) -> Optional[int]:
        """Soma da duração das faixas na fila (None se alguma for live)."""
        if any(t.duration is None for t in self.itens):
            return None
        return sum(t.duration or 0 for t in self.itens)

    def adicionar(self, track: Track) -> bool:
        """
        Enfileira uma faixa.

        Returns:
            False se a fila está cheia
        """
        if self.cheia:
            return False
        self.itens.append(track)
        return True

    def proxima(self) -> Optional[Track]:
        """
        Avança para a próxima faixa, respeitando o modo de loop.

        Returns:
            A faixa que deve tocar agora, ou None se a fila acabou
        """
        anterior = self.atual

        # LoopMode.TRACK repete a faixa atual sem consumir a fila
        if self.loop is LoopMode.TRACK and anterior is not None:
            return anterior

        if anterior is not None:
            self.historico.append(anterior)
            # LoopMode.QUEUE devolve a faixa para o fim do rodízio
            if self.loop is LoopMode.QUEUE:
                self.itens.append(anterior)

        self.atual = self.itens.popleft() if self.itens else None
        return self.atual

    def pular(self) -> Optional[Track]:
        """
        Pula a faixa atual.

        Diferente de ``proxima``, ignora LoopMode.TRACK — quem pediu /skip
        quer sair da faixa, não repeti-la de novo.
        """
        if self.loop is LoopMode.TRACK:
            self.loop = LoopMode.OFF if not self.itens else self.loop
            if self.loop is LoopMode.TRACK:
                # Mantém o loop de fila, mas força a troca de faixa
                self.loop = LoopMode.QUEUE
        return self.proxima()

    def embaralhar(self) -> None:
        """Embaralha as faixas aguardando (não mexe na que está tocando)."""
        itens = list(self.itens)
        random.shuffle(itens)
        self.itens = deque(itens)

    def remover(self, posicao: int) -> Optional[Track]:
        """
        Remove uma faixa pela posição exibida ao usuário (1-indexada).

        Args:
            posicao: Índice começando em 1

        Returns:
            A faixa removida, ou None se a posição é inválida
        """
        if posicao < 1 or posicao > len(self.itens):
            return None

        itens = list(self.itens)
        removida = itens.pop(posicao - 1)
        self.itens = deque(itens)
        return removida

    def mover(self, origem: int, destino: int) -> Optional[Track]:
        """
        Move uma faixa de posição (ambas 1-indexadas).

        Returns:
            A faixa movida, ou None se alguma posição é inválida
        """
        total = len(self.itens)
        if not (1 <= origem <= total and 1 <= destino <= total):
            return None

        itens = list(self.itens)
        faixa = itens.pop(origem - 1)
        itens.insert(destino - 1, faixa)
        self.itens = deque(itens)
        return faixa

    def limpar(self) -> int:
        """Esvazia a fila. Retorna quantas faixas foram removidas."""
        total = len(self.itens)
        self.itens.clear()
        return total

    def resetar(self) -> None:
        """Limpa tudo, inclusive a faixa atual e o modo de loop."""
        self.itens.clear()
        self.historico.clear()
        self.atual = None
        self.loop = LoopMode.OFF

    def pagina(self, numero: int, por_pagina: int = 10) -> List[Track]:
        """
        Retorna uma página da fila (1-indexada).

        Args:
            numero: Número da página
            por_pagina: Itens por página

        Returns:
            Lista de faixas da página
        """
        inicio = (numero - 1) * por_pagina
        return list(self.itens)[inicio : inicio + por_pagina]

    @property
    def total_paginas(self) -> int:
        """Quantidade de páginas da fila (mínimo 1)."""
        if not self.itens:
            return 1
        return (len(self.itens) + 9) // 10

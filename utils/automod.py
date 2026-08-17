"""
CLUTCH BOT - REGRAS DE AUTOMOD
==============================

Detecção pura (sem discord.py) para poder ser testada isoladamente.

Regras cobertas:
- **Spam**: N mensagens numa janela de tempo
- **Flood repetido**: a mesma mensagem várias vezes seguidas
- **Convites**: links de convite para outros servidores
- **Links**: qualquer URL (opcional, para canais fechados)
- **Menções em massa**: muitas menções numa mensagem só
- **CAPS**: mensagem majoritariamente em maiúsculas
- **Palavras proibidas**: lista configurável por servidor

O rastreamento de spam é feito por janela deslizante em memória, por
(servidor, usuário) — nada disso vai ao banco no caminho quente.
"""

import re
import time
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, List, Optional, Tuple

# Convites do Discord, incluindo os domínios alternativos
INVITE_RE = re.compile(
    r"(?:discord(?:\.gg|(?:app)?\.com/invite|\.me)|dsc\.gg|invite\.gg)/[a-z0-9-]+",
    re.IGNORECASE,
)

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

# Menções de usuário, cargo e @everyone/@here
MENCAO_RE = re.compile(r"<@[!&]?\d+>|@everyone|@here")

# Caracteres que sobram depois de tirar marcação e espaços
SO_LETRAS_RE = re.compile(r"[^A-Za-zÀ-ÿ]")

# Emojis customizados do Discord: <:nome:123> e <a:nome:123>
EMOJI_CUSTOM_RE = re.compile(r"<a?:\w+:\d+>")


class Violacao(str, Enum):
    """Tipo de infração detectada."""

    SPAM = "spam"
    FLOOD = "flood"
    CONVITE = "convite"
    LINK = "link"
    MENCOES = "mencoes"
    CAPS = "caps"
    PALAVRA = "palavra"

    @property
    def descricao(self) -> str:
        """Texto exibido ao usuário e no log."""
        return {
            Violacao.SPAM: "envio de mensagens rápido demais",
            Violacao.FLOOD: "mensagem repetida várias vezes",
            Violacao.CONVITE: "convite para outro servidor",
            Violacao.LINK: "link não permitido",
            Violacao.MENCOES: "menções em massa",
            Violacao.CAPS: "excesso de letras maiúsculas",
            Violacao.PALAVRA: "palavra proibida",
        }[self]


@dataclass(frozen=True)
class RegrasAutomod:
    """
    Configuração de automod de um servidor.

    Cada limite em 0 (ou lista vazia) desliga a regra correspondente.
    """

    ativo: bool = False

    # Spam: máximo de mensagens dentro da janela
    spam_mensagens: int = 5
    spam_janela_segundos: int = 5

    # Flood: mesma mensagem repetida N vezes seguidas
    flood_repeticoes: int = 3

    bloquear_convites: bool = True
    bloquear_links: bool = False

    # Menções por mensagem
    max_mencoes: int = 5

    # CAPS: percentual de maiúsculas a partir de quantos caracteres
    caps_percentual: int = 70
    caps_minimo_caracteres: int = 10

    palavras_proibidas: Tuple[str, ...] = ()

    # Punição automática ao acumular advertências (0 = só apagar e avisar)
    castigo_minutos: int = 10
    avisos_para_castigo: int = 3


@dataclass
class Deteccao:
    """Resultado de uma checagem."""

    violacao: Violacao
    detalhe: str = ""

    def __str__(self) -> str:
        return f"{self.violacao.descricao}{f' ({self.detalhe})' if self.detalhe else ''}"


def normalizar(texto: str) -> str:
    """
    Normaliza texto para comparar palavras proibidas.

    Remove acentos e baixa a caixa, para que "PÃO" e "pao" batam com a mesma
    entrada da lista. Não tenta resolver leetspeak — a ideia é reduzir falso
    negativo óbvio, não travar uma guerra de evasão.
    """
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.casefold()


def contem_palavra_proibida(texto: str, palavras: Tuple[str, ...]) -> Optional[str]:
    """
    Procura palavras proibidas no texto.

    Compara por palavra inteira: "assado" não dispara por conter "ass".

    Args:
        texto: Conteúdo da mensagem
        palavras: Lista de termos proibidos

    Returns:
        A palavra encontrada, ou None
    """
    if not palavras:
        return None

    normalizado = normalizar(texto)
    # Divide em tokens alfanuméricos, ignorando pontuação
    tokens = set(re.findall(r"\w+", normalizado))

    for palavra in palavras:
        alvo = normalizar(palavra).strip()
        if not alvo:
            continue
        # Expressões com espaço são buscadas como substring
        if " " in alvo:
            if alvo in normalizado:
                return palavra
        elif alvo in tokens:
            return palavra

    return None


def percentual_de_caps(texto: str) -> int:
    """
    Calcula o percentual de letras maiúsculas.

    URLs, menções e emojis customizados saem da conta antes da medição: as
    letras minúsculas de um link diluíam o percentual e faziam um grito
    legítimo passar batido ("QUE ABSURDO https://site.com/pagina" caía de
    100% para menos de 60%).

    Números e pontuação também não entram: só letras contam.

    Args:
        texto: Conteúdo da mensagem

    Returns:
        Percentual de 0 a 100 (0 se não houver letras)
    """
    # INVITE_RE além de URL_RE: "discord.gg/abc" não tem esquema http e
    # escaparia da limpeza, voltando a diluir a contagem
    limpo = URL_RE.sub(" ", texto)
    limpo = INVITE_RE.sub(" ", limpo)
    limpo = EMOJI_CUSTOM_RE.sub(" ", limpo)
    limpo = MENCAO_RE.sub(" ", limpo)

    letras = SO_LETRAS_RE.sub("", limpo)
    if not letras:
        return 0

    maiusculas = sum(1 for c in letras if c.isupper())
    return round(maiusculas * 100 / len(letras))


def contar_mencoes(texto: str) -> int:
    """Conta menções de usuário, cargo e @everyone/@here no texto."""
    return len(MENCAO_RE.findall(texto))


@dataclass
class RastreadorDeSpam:
    """
    Janela deslizante de mensagens por usuário.

    Mantém só os timestamps dentro da janela; entradas velhas saem sozinhas
    a cada registro, então a memória não cresce com o tempo.
    """

    janela_segundos: int = 5
    _historico: Dict[Tuple[int, int], Deque[Tuple[float, str]]] = field(
        default_factory=lambda: defaultdict(deque)
    )

    def registrar(
        self,
        guild_id: int,
        user_id: int,
        conteudo: str,
        agora: Optional[float] = None,
    ) -> Tuple[int, int]:
        """
        Registra uma mensagem e devolve os contadores da janela.

        Args:
            guild_id: Servidor
            user_id: Autor
            conteudo: Texto da mensagem
            agora: Timestamp (para testes)

        Returns:
            (mensagens na janela, repetições consecutivas do mesmo texto)
        """
        agora = time.monotonic() if agora is None else agora
        chave = (guild_id, user_id)
        fila = self._historico[chave]

        limite = agora - self.janela_segundos
        while fila and fila[0][0] < limite:
            fila.popleft()

        fila.append((agora, conteudo.strip()))

        # Repetições consecutivas contadas do fim para o começo
        repeticoes = 0
        alvo = conteudo.strip()
        if alvo:
            for _, texto in reversed(fila):
                if texto != alvo:
                    break
                repeticoes += 1

        return len(fila), repeticoes

    def limpar_usuario(self, guild_id: int, user_id: int) -> None:
        """Zera o histórico de um usuário (após punição)."""
        self._historico.pop((guild_id, user_id), None)

    def podar(self, agora: Optional[float] = None) -> int:
        """
        Remove usuários sem mensagens recentes.

        Chamado periodicamente para o dicionário não acumular quem falou uma
        vez e sumiu.

        Returns:
            Quantidade de entradas removidas
        """
        agora = time.monotonic() if agora is None else agora
        limite = agora - self.janela_segundos

        vazias = [
            chave
            for chave, fila in self._historico.items()
            if not fila or fila[-1][0] < limite
        ]
        for chave in vazias:
            del self._historico[chave]

        return len(vazias)

    @property
    def tamanho(self) -> int:
        """Quantidade de usuários rastreados."""
        return len(self._historico)


def analisar(
    conteudo: str,
    regras: RegrasAutomod,
    mensagens_na_janela: int = 0,
    repeticoes: int = 0,
) -> List[Deteccao]:
    """
    Aplica todas as regras a uma mensagem.

    Args:
        conteudo: Texto da mensagem
        regras: Configuração do servidor
        mensagens_na_janela: Contador vindo do RastreadorDeSpam
        repeticoes: Repetições consecutivas do mesmo texto

    Returns:
        Lista de detecções (vazia se a mensagem está limpa)
    """
    if not regras.ativo:
        return []

    deteccoes: List[Deteccao] = []

    if regras.spam_mensagens and mensagens_na_janela > regras.spam_mensagens:
        deteccoes.append(
            Deteccao(
                Violacao.SPAM,
                f"{mensagens_na_janela} msgs em {regras.spam_janela_segundos}s",
            )
        )

    if regras.flood_repeticoes and repeticoes >= regras.flood_repeticoes:
        deteccoes.append(Deteccao(Violacao.FLOOD, f"{repeticoes}x seguidas"))

    if regras.bloquear_convites and INVITE_RE.search(conteudo):
        deteccoes.append(Deteccao(Violacao.CONVITE))

    # Um convite já é um link: não reporta os dois pela mesma URL
    elif regras.bloquear_links and URL_RE.search(conteudo):
        deteccoes.append(Deteccao(Violacao.LINK))

    if regras.max_mencoes:
        mencoes = contar_mencoes(conteudo)
        if mencoes > regras.max_mencoes:
            deteccoes.append(Deteccao(Violacao.MENCOES, f"{mencoes} menções"))

    if regras.caps_percentual and len(conteudo) >= regras.caps_minimo_caracteres:
        percentual = percentual_de_caps(conteudo)
        if percentual >= regras.caps_percentual:
            deteccoes.append(Deteccao(Violacao.CAPS, f"{percentual}%"))

    palavra = contem_palavra_proibida(conteudo, regras.palavras_proibidas)
    if palavra:
        deteccoes.append(Deteccao(Violacao.PALAVRA, palavra))

    return deteccoes

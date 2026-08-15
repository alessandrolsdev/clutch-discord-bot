"""
CLUTCH BOT - UTILITÁRIOS DE MIXAGEM PCM
=======================================

Funções puras para manipular frames de áudio PCM 16-bit estéreo no formato
que o Discord espera (20ms @ 48kHz = 960 samples = 3840 bytes).

Por que existe:
- ``audioop.add``/``audioop.mul`` exigem fragmentos com o mesmo tamanho e
  múltiplos do sample width. Datagramas UDP e a saída do FFmpeg chegam com
  tamanhos variados, o que fazia o mixer levantar exceção no meio do stream.
- ``audioop`` foi removido do Python 3.13; aqui há um fallback em numpy.
"""

from typing import Optional

# 20ms de PCM 16-bit estéreo a 48kHz: 960 samples * 2 canais * 2 bytes
FRAME_BYTES = 3840
SAMPLE_WIDTH = 2
SILENCE = b"\x00" * FRAME_BYTES

try:  # pragma: no cover - depende da versão do Python
    import audioop  # type: ignore

    _HAS_AUDIOOP = True
except ImportError:  # pragma: no cover - Python 3.13+
    audioop = None  # type: ignore
    _HAS_AUDIOOP = False

try:  # pragma: no cover - numpy é opcional para o fallback
    import numpy as _np
except ImportError:  # pragma: no cover
    _np = None


def normalize_frame(data: Optional[bytes], size: int = FRAME_BYTES) -> bytes:
    """
    Ajusta um fragmento de áudio para exatamente ``size`` bytes.

    Fragmentos curtos são preenchidos com silêncio; longos são truncados.
    Também alinha o tamanho ao sample width para não cortar uma amostra ao meio.

    Args:
        data: Fragmento PCM (pode ser None ou vazio)
        size: Tamanho alvo em bytes

    Returns:
        bytes: Fragmento com exatamente ``size`` bytes
    """
    if not data:
        return b"\x00" * size

    if len(data) > size:
        return data[:size]

    if len(data) < size:
        return data + b"\x00" * (size - len(data))

    return data


def scale_volume(data: bytes, volume: float) -> bytes:
    """
    Aplica um multiplicador de volume a um frame PCM 16-bit.

    Args:
        data: Frame PCM já normalizado
        volume: Multiplicador (1.0 = sem alteração)

    Returns:
        bytes: Frame com volume aplicado (o original em caso de falha)
    """
    if volume == 1.0:
        return data
    if volume <= 0.0:
        return b"\x00" * len(data)

    if _HAS_AUDIOOP:
        try:
            return audioop.mul(data, SAMPLE_WIDTH, volume)
        except audioop.error:
            return data

    if _np is not None:
        samples = _np.frombuffer(data, dtype="<i2").astype("<i4")
        scaled = _np.clip(samples * volume, -32768, 32767).astype("<i2")
        return scaled.tobytes()

    return data


def mix_frames(a: bytes, b: bytes) -> bytes:
    """
    Soma dois frames PCM 16-bit com saturação (sem wrap-around).

    Args:
        a: Primeiro frame (já normalizado)
        b: Segundo frame (já normalizado)

    Returns:
        bytes: Frame resultante da soma
    """
    if len(a) != len(b):
        size = max(len(a), len(b))
        a, b = normalize_frame(a, size), normalize_frame(b, size)

    if _HAS_AUDIOOP:
        try:
            return audioop.add(a, b, SAMPLE_WIDTH)
        except audioop.error:
            return a

    if _np is not None:
        left = _np.frombuffer(a, dtype="<i2").astype("<i4")
        right = _np.frombuffer(b, dtype="<i2").astype("<i4")
        mixed = _np.clip(left + right, -32768, 32767).astype("<i2")
        return mixed.tobytes()

    return a

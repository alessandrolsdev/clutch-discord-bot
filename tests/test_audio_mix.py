"""Testes das funções puras de mixagem PCM."""

import unittest

from utils.audio_mix import FRAME_BYTES, mix_frames, normalize_frame, scale_volume


def pcm(*valores: int) -> bytes:
    """Monta um fragmento PCM 16-bit little-endian a partir de amostras."""
    return b"".join(int(v).to_bytes(2, "little", signed=True) for v in valores)


def amostras(data: bytes) -> list:
    """Converte um fragmento PCM de volta para inteiros."""
    return [
        int.from_bytes(data[i : i + 2], "little", signed=True)
        for i in range(0, len(data), 2)
    ]


class NormalizeFrameTests(unittest.TestCase):
    def test_preenche_fragmento_curto_com_silencio(self) -> None:
        resultado = normalize_frame(pcm(100, 200))
        self.assertEqual(len(resultado), FRAME_BYTES)
        self.assertEqual(amostras(resultado)[:2], [100, 200])
        self.assertEqual(set(amostras(resultado)[2:]), {0})

    def test_trunca_fragmento_longo(self) -> None:
        resultado = normalize_frame(b"\x01\x02" * (FRAME_BYTES // 2 + 500))
        self.assertEqual(len(resultado), FRAME_BYTES)

    def test_none_e_vazio_viram_silencio(self) -> None:
        self.assertEqual(normalize_frame(None), b"\x00" * FRAME_BYTES)
        self.assertEqual(normalize_frame(b""), b"\x00" * FRAME_BYTES)


class ScaleVolumeTests(unittest.TestCase):
    def test_volume_1_nao_altera(self) -> None:
        dados = pcm(1000, -1000)
        self.assertEqual(scale_volume(dados, 1.0), dados)

    def test_volume_zero_silencia(self) -> None:
        resultado = scale_volume(pcm(1000, -1000), 0.0)
        self.assertEqual(set(amostras(resultado)), {0})

    def test_volume_reduz_amplitude(self) -> None:
        resultado = amostras(scale_volume(pcm(1000, -1000), 0.5))
        self.assertEqual(resultado, [500, -500])


class MixFramesTests(unittest.TestCase):
    def test_soma_amostras(self) -> None:
        resultado = amostras(mix_frames(pcm(100, -100), pcm(50, -50)))
        self.assertEqual(resultado, [150, -150])

    def test_satura_em_vez_de_dar_wrap(self) -> None:
        # Sem saturação, 30000 + 30000 estouraria para um valor negativo
        resultado = amostras(mix_frames(pcm(30000), pcm(30000)))
        self.assertEqual(resultado, [32767])

    def test_tamanhos_diferentes_nao_levantam_erro(self) -> None:
        # Era exatamente este caso que quebrava o mixer: audioop.add exige
        # fragmentos do mesmo tamanho e o datagrama UDP nem sempre tinha 3840B
        resultado = mix_frames(pcm(10, 20, 30), pcm(1))
        self.assertEqual(amostras(resultado), [11, 20, 30])


if __name__ == "__main__":
    unittest.main()

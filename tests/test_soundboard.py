"""Testes da resolução de nomes do soundboard (proteção contra path traversal)."""

import tempfile
import unittest
from pathlib import Path

from utils.soundboard import listar_sons, resolver_som


class SoundboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self._tmp.name)
        self.sons = self.raiz / "sfx"
        self.sons.mkdir()

        (self.sons / "alarme.mp3").write_bytes(b"fake")
        (self.sons / "buzina.wav").write_bytes(b"fake")
        (self.sons / "notas.txt").write_text("não é som")

        # Arquivo sensível fora da pasta de sons, alvo do path traversal
        (self.raiz / "segredo.mp3").write_bytes(b"segredo")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_lista_apenas_arquivos_de_audio(self) -> None:
        self.assertEqual(listar_sons(self.sons), ["alarme.mp3", "buzina.wav"])

    def test_lista_vazia_se_diretorio_nao_existe(self) -> None:
        self.assertEqual(listar_sons(self.raiz / "inexistente"), [])

    def test_resolve_com_e_sem_extensao(self) -> None:
        self.assertEqual(resolver_som(self.sons, "alarme.mp3").name, "alarme.mp3")
        self.assertEqual(resolver_som(self.sons, "alarme").name, "alarme.mp3")
        self.assertEqual(resolver_som(self.sons, "buzina").name, "buzina.wav")

    def test_bloqueia_path_traversal(self) -> None:
        for entrada in (
            "../segredo.mp3",
            "../../segredo.mp3",
            "..\\segredo.mp3",
            "/etc/passwd",
            str(self.raiz / "segredo.mp3"),
        ):
            with self.subTest(entrada=entrada):
                self.assertIsNone(resolver_som(self.sons, entrada))

    def test_rejeita_extensao_invalida_e_entradas_vazias(self) -> None:
        self.assertIsNone(resolver_som(self.sons, "notas.txt"))
        self.assertIsNone(resolver_som(self.sons, ""))
        self.assertIsNone(resolver_som(self.sons, None))
        self.assertIsNone(resolver_som(self.sons, "   "))

    def test_arquivo_inexistente(self) -> None:
        self.assertIsNone(resolver_som(self.sons, "nao_existe"))


if __name__ == "__main__":
    unittest.main()

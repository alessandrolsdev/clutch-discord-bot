"""Testes da fila de música (lógica pura, sem discord.py)."""

import unittest

from utils.musica_fila import (
    Fila,
    LoopMode,
    Track,
    barra_progresso,
    formatar_duracao,
)


def faixa(nome: str, duracao: int = 100) -> Track:
    """Cria uma faixa de teste."""
    return Track(title=nome, stream_url=f"http://exemplo/{nome}", duration=duracao)


class FormatacaoTests(unittest.TestCase):
    def test_formata_minutos_e_horas(self) -> None:
        self.assertEqual(formatar_duracao(65), "1:05")
        self.assertEqual(formatar_duracao(3725), "1:02:05")
        self.assertEqual(formatar_duracao(0), "──:──")
        self.assertEqual(formatar_duracao(None), "──:──")

    def test_barra_de_progresso(self) -> None:
        barra = barra_progresso(0, 100, tamanho=10)
        self.assertTrue(barra.startswith("🔘"))
        self.assertEqual(len(barra.replace("🔘", "").replace("▬", "")), 0)

        # Live (sem duração) tem tratamento próprio
        self.assertEqual(barra_progresso(10, None), "🔴 AO VIVO")

    def test_barra_nao_estoura_no_fim(self) -> None:
        barra = barra_progresso(999, 100, tamanho=10)
        self.assertEqual(barra.count("🔘"), 1)
        self.assertEqual(barra.count("▬"), 9)


class FilaBasicaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fila = Fila(limite=3)

    def test_adiciona_e_respeita_limite(self) -> None:
        self.assertTrue(self.fila.adicionar(faixa("a")))
        self.assertTrue(self.fila.adicionar(faixa("b")))
        self.assertTrue(self.fila.adicionar(faixa("c")))
        self.assertFalse(self.fila.adicionar(faixa("d")))
        self.assertEqual(len(self.fila), 3)

    def test_proxima_consome_na_ordem(self) -> None:
        for nome in "abc":
            self.fila.adicionar(faixa(nome))

        self.assertEqual(self.fila.proxima().title, "a")
        self.assertEqual(self.fila.proxima().title, "b")
        self.assertEqual(self.fila.proxima().title, "c")
        self.assertIsNone(self.fila.proxima())

    def test_remover_por_posicao(self) -> None:
        for nome in "abc":
            self.fila.adicionar(faixa(nome))

        self.assertEqual(self.fila.remover(2).title, "b")
        self.assertEqual([t.title for t in self.fila.itens], ["a", "c"])
        self.assertIsNone(self.fila.remover(99))
        self.assertIsNone(self.fila.remover(0))

    def test_mover_reordena(self) -> None:
        for nome in "abc":
            self.fila.adicionar(faixa(nome))

        self.assertEqual(self.fila.mover(3, 1).title, "c")
        self.assertEqual([t.title for t in self.fila.itens], ["c", "a", "b"])
        self.assertIsNone(self.fila.mover(1, 99))

    def test_duracao_total_e_none_com_live(self) -> None:
        self.fila.adicionar(faixa("a", 60))
        self.fila.adicionar(faixa("b", 30))
        self.assertEqual(self.fila.duracao_total, 90)

        self.fila.adicionar(Track(title="live", stream_url="x", duration=None))
        self.assertIsNone(self.fila.duracao_total)

    def test_limpar_e_resetar(self) -> None:
        for nome in "abc":
            self.fila.adicionar(faixa(nome))
        self.fila.proxima()

        self.assertEqual(self.fila.limpar(), 2)
        self.assertIsNotNone(self.fila.atual)  # limpar não mexe na faixa atual

        self.fila.resetar()
        self.assertIsNone(self.fila.atual)
        self.assertIs(self.fila.loop, LoopMode.OFF)


class LoopTests(unittest.TestCase):
    def test_loop_track_repete_a_mesma_faixa(self) -> None:
        fila = Fila()
        fila.adicionar(faixa("a"))
        fila.adicionar(faixa("b"))

        self.assertEqual(fila.proxima().title, "a")
        fila.loop = LoopMode.TRACK

        self.assertEqual(fila.proxima().title, "a")
        self.assertEqual(fila.proxima().title, "a")
        # A fila não foi consumida
        self.assertEqual(len(fila), 1)

    def test_loop_queue_reenfileira_no_fim(self) -> None:
        fila = Fila()
        fila.adicionar(faixa("a"))
        fila.adicionar(faixa("b"))
        fila.loop = LoopMode.QUEUE

        self.assertEqual(fila.proxima().title, "a")
        self.assertEqual(fila.proxima().title, "b")
        # "a" voltou para o fim ao ser substituída
        self.assertEqual(fila.proxima().title, "a")

    def test_pular_sai_da_faixa_mesmo_em_loop_track(self) -> None:
        fila = Fila()
        fila.adicionar(faixa("a"))
        fila.adicionar(faixa("b"))

        self.assertEqual(fila.proxima().title, "a")
        fila.loop = LoopMode.TRACK

        # /skip precisa avançar de verdade, senão o usuário fica preso
        self.assertEqual(fila.pular().title, "b")

    def test_loop_off_termina_a_fila(self) -> None:
        fila = Fila()
        fila.adicionar(faixa("a"))

        self.assertEqual(fila.proxima().title, "a")
        self.assertIsNone(fila.proxima())


class HistoricoEPaginacaoTests(unittest.TestCase):
    def test_historico_guarda_faixas_tocadas(self) -> None:
        fila = Fila()
        for nome in "abc":
            fila.adicionar(faixa(nome))

        fila.proxima()
        fila.proxima()

        self.assertEqual([t.title for t in fila.historico], ["a"])

    def test_paginacao(self) -> None:
        fila = Fila(limite=25)
        for i in range(25):
            fila.adicionar(faixa(f"faixa{i}"))

        self.assertEqual(fila.total_paginas, 3)
        self.assertEqual(len(fila.pagina(1)), 10)
        self.assertEqual(len(fila.pagina(3)), 5)
        self.assertEqual(fila.pagina(1)[0].title, "faixa0")
        self.assertEqual(fila.pagina(2)[0].title, "faixa10")

    def test_embaralhar_preserva_as_faixas(self) -> None:
        fila = Fila(limite=50)
        nomes = [f"faixa{i}" for i in range(20)]
        for nome in nomes:
            fila.adicionar(faixa(nome))

        fila.embaralhar()

        self.assertEqual(sorted(t.title for t in fila.itens), sorted(nomes))
        self.assertEqual(len(fila), 20)


if __name__ == "__main__":
    unittest.main()

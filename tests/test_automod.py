"""
Testes das regras de automod.

Falso positivo em automod é pior que falso negativo — um filtro que apaga
mensagem legítima faz o servidor desligar a função inteira. Por isso boa parte
destes testes verifica o que **não** deve disparar.
"""

import unittest

from utils.automod import (
    Deteccao,
    RastreadorDeSpam,
    RegrasAutomod,
    Violacao,
    analisar,
    contar_mencoes,
    contem_palavra_proibida,
    normalizar,
    percentual_de_caps,
)

REGRAS_PADRAO = RegrasAutomod(ativo=True)


def tipos(deteccoes) -> set:
    """Extrai os tipos de violação de uma lista de detecções."""
    return {d.violacao for d in deteccoes}


class NormalizacaoTests(unittest.TestCase):
    def test_remove_acentos_e_caixa(self) -> None:
        self.assertEqual(normalizar("PÃO Ção"), "pao cao")
        self.assertEqual(normalizar("ÀÉÎÕÜ"), "aeiou")


class PalavraProibidaTests(unittest.TestCase):
    def test_encontra_palavra_exata(self) -> None:
        self.assertEqual(contem_palavra_proibida("isso é lixo", ("lixo",)), "lixo")

    def test_ignora_acentos_e_caixa(self) -> None:
        self.assertEqual(contem_palavra_proibida("SEU IDIÔTA", ("idiota",)), "idiota")

    def test_nao_pega_substring_de_outra_palavra(self) -> None:
        # O clássico problema de "Scunthorpe": "assado" não pode disparar por "ass"
        self.assertIsNone(contem_palavra_proibida("frango assado", ("ass",)))
        self.assertIsNone(contem_palavra_proibida("classe de matemática", ("lass",)))

    def test_ignora_pontuacao_ao_redor(self) -> None:
        self.assertEqual(contem_palavra_proibida("que lixo!", ("lixo",)), "lixo")
        self.assertEqual(contem_palavra_proibida("(lixo)", ("lixo",)), "lixo")

    def test_expressao_com_espaco_busca_substring(self) -> None:
        self.assertEqual(
            contem_palavra_proibida("compre seguidores agora", ("compre seguidores",)),
            "compre seguidores",
        )

    def test_lista_vazia_nunca_dispara(self) -> None:
        self.assertIsNone(contem_palavra_proibida("qualquer coisa", ()))


class CapsTests(unittest.TestCase):
    def test_calcula_percentual_apenas_de_letras(self) -> None:
        self.assertEqual(percentual_de_caps("ABCD"), 100)
        self.assertEqual(percentual_de_caps("abcd"), 0)
        self.assertEqual(percentual_de_caps("ABcd"), 50)

    def test_ignora_numeros_e_pontuacao(self) -> None:
        # Só as letras entram na conta: "1234!!!" não é grito
        self.assertEqual(percentual_de_caps("1234!!! ABCD"), 100)
        self.assertEqual(percentual_de_caps("12345!!!"), 0)

    def test_mensagem_curta_nao_dispara(self) -> None:
        regras = RegrasAutomod(ativo=True, caps_minimo_caracteres=10)
        # "OK!" é maiúscula, mas curta demais para ser grito
        self.assertNotIn(Violacao.CAPS, tipos(analisar("OK!", regras)))

    def test_grito_longo_dispara(self) -> None:
        deteccoes = analisar("ALGUEM ME AJUDA AQUI AGORA", REGRAS_PADRAO)
        self.assertIn(Violacao.CAPS, tipos(deteccoes))


class MencoesTests(unittest.TestCase):
    def test_conta_usuarios_cargos_e_everyone(self) -> None:
        texto = "<@123> <@!456> <@&789> @everyone @here"
        self.assertEqual(contar_mencoes(texto), 5)

    def test_menciona_pouco_nao_dispara(self) -> None:
        deteccoes = analisar("oi <@1> <@2>", REGRAS_PADRAO)
        self.assertNotIn(Violacao.MENCOES, tipos(deteccoes))

    def test_mencao_em_massa_dispara(self) -> None:
        texto = " ".join(f"<@{i}>" for i in range(10))
        self.assertIn(Violacao.MENCOES, tipos(analisar(texto, REGRAS_PADRAO)))


class ConviteELinkTests(unittest.TestCase):
    def test_detecta_variacoes_de_convite(self) -> None:
        for texto in (
            "entra ai discord.gg/abc123",
            "https://discord.com/invite/xyz",
            "http://discordapp.com/invite/xyz",
            "olha dsc.gg/servidor",
            "DISCORD.GG/MAIUSCULO",
        ):
            with self.subTest(texto=texto):
                self.assertIn(Violacao.CONVITE, tipos(analisar(texto, REGRAS_PADRAO)))

    def test_link_normal_nao_dispara_por_padrao(self) -> None:
        # bloquear_links é False por padrão
        deteccoes = analisar("veja https://github.com/exemplo", REGRAS_PADRAO)
        self.assertEqual(tipos(deteccoes), set())

    def test_link_dispara_quando_ligado(self) -> None:
        regras = RegrasAutomod(ativo=True, bloquear_links=True)
        deteccoes = analisar("veja https://github.com/exemplo", regras)
        self.assertIn(Violacao.LINK, tipos(deteccoes))

    def test_convite_nao_reporta_link_duplicado(self) -> None:
        regras = RegrasAutomod(ativo=True, bloquear_links=True)
        deteccoes = analisar("https://discord.gg/abc", regras)

        # Reporta convite, não convite + link pela mesma URL
        self.assertIn(Violacao.CONVITE, tipos(deteccoes))
        self.assertNotIn(Violacao.LINK, tipos(deteccoes))

    def test_convite_desligado_nao_dispara(self) -> None:
        regras = RegrasAutomod(ativo=True, bloquear_convites=False)
        self.assertEqual(tipos(analisar("discord.gg/abc", regras)), set())


class RastreadorTests(unittest.TestCase):
    def test_conta_mensagens_dentro_da_janela(self) -> None:
        rastreador = RastreadorDeSpam(janela_segundos=5)

        for i in range(3):
            total, _ = rastreador.registrar(1, 42, f"msg{i}", agora=100.0 + i)

        self.assertEqual(total, 3)

    def test_mensagens_antigas_saem_da_janela(self) -> None:
        rastreador = RastreadorDeSpam(janela_segundos=5)

        rastreador.registrar(1, 42, "antiga", agora=100.0)
        total, _ = rastreador.registrar(1, 42, "nova", agora=110.0)

        # A de 100.0 saiu da janela de 5s
        self.assertEqual(total, 1)

    def test_conta_repeticoes_consecutivas(self) -> None:
        rastreador = RastreadorDeSpam(janela_segundos=30)

        for i in range(3):
            _, repeticoes = rastreador.registrar(1, 42, "mesma coisa", agora=100.0 + i)

        self.assertEqual(repeticoes, 3)

    def test_mensagem_diferente_zera_a_sequencia(self) -> None:
        rastreador = RastreadorDeSpam(janela_segundos=30)

        rastreador.registrar(1, 42, "a", agora=100.0)
        rastreador.registrar(1, 42, "a", agora=101.0)
        _, repeticoes = rastreador.registrar(1, 42, "b", agora=102.0)

        self.assertEqual(repeticoes, 1)

    def test_usuarios_e_servidores_sao_independentes(self) -> None:
        rastreador = RastreadorDeSpam(janela_segundos=30)

        rastreador.registrar(1, 42, "x", agora=100.0)
        rastreador.registrar(1, 43, "x", agora=100.0)
        total_outro_servidor, _ = rastreador.registrar(2, 42, "x", agora=100.0)

        self.assertEqual(total_outro_servidor, 1)
        self.assertEqual(rastreador.tamanho, 3)

    def test_podar_remove_inativos(self) -> None:
        rastreador = RastreadorDeSpam(janela_segundos=5)

        rastreador.registrar(1, 42, "x", agora=100.0)
        rastreador.registrar(1, 43, "y", agora=200.0)

        removidos = rastreador.podar(agora=201.0)

        self.assertEqual(removidos, 1)
        self.assertEqual(rastreador.tamanho, 1)

    def test_limpar_usuario(self) -> None:
        rastreador = RastreadorDeSpam()
        rastreador.registrar(1, 42, "x")

        rastreador.limpar_usuario(1, 42)

        self.assertEqual(rastreador.tamanho, 0)


class AnalisarTests(unittest.TestCase):
    def test_automod_desligado_nunca_dispara(self) -> None:
        regras = RegrasAutomod(ativo=False)
        texto = "discord.gg/abc GRITANDO MUITO AQUI @everyone @everyone"

        self.assertEqual(analisar(texto, regras, 999, 999), [])

    def test_mensagem_normal_passa_limpa(self) -> None:
        for texto in (
            "oi pessoal, tudo bem?",
            "vamos jogar hoje as 20h",
            "https://github.com/exemplo/repo",
            "ok",
            "KKKKK",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(analisar(texto, REGRAS_PADRAO, 1, 1), [])

    def test_spam_dispara_acima_do_limite(self) -> None:
        regras = RegrasAutomod(ativo=True, spam_mensagens=5)

        self.assertEqual(analisar("oi", regras, 5, 1), [])  # no limite, ainda ok
        self.assertIn(Violacao.SPAM, tipos(analisar("oi", regras, 6, 1)))

    def test_flood_dispara_no_limite(self) -> None:
        regras = RegrasAutomod(ativo=True, flood_repeticoes=3)

        self.assertEqual(tipos(analisar("oi", regras, 1, 2)), set())
        self.assertIn(Violacao.FLOOD, tipos(analisar("oi", regras, 1, 3)))

    def test_limites_zerados_desligam_regras(self) -> None:
        regras = RegrasAutomod(
            ativo=True,
            spam_mensagens=0,
            flood_repeticoes=0,
            max_mencoes=0,
            caps_percentual=0,
            bloquear_convites=False,
        )
        texto = "GRITO TOTAL AQUI " + " ".join(f"<@{i}>" for i in range(20))

        self.assertEqual(analisar(texto, regras, 999, 999), [])

    def test_multiplas_violacoes_sao_reportadas_juntas(self) -> None:
        regras = RegrasAutomod(ativo=True, palavras_proibidas=("lixo",))
        texto = "QUE LIXO DE SERVIDOR discord.gg/abc"

        encontrados = tipos(analisar(texto, regras, 1, 1))

        self.assertIn(Violacao.CONVITE, encontrados)
        self.assertIn(Violacao.CAPS, encontrados)
        self.assertIn(Violacao.PALAVRA, encontrados)

    def test_deteccao_tem_descricao_legivel(self) -> None:
        deteccao = Deteccao(Violacao.SPAM, "6 msgs em 5s")
        self.assertIn("rápido demais", str(deteccao))
        self.assertIn("6 msgs", str(deteccao))


if __name__ == "__main__":
    unittest.main()

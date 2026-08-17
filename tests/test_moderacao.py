"""
Testes da validação de hierarquia da moderação.

É a checagem com maior consequência do bot: um furo aqui deixa um moderador
banir alguém acima dele, ou o bot tentar punir quem não pode (erro 403 da API).
"""

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("DISCORD_TOKEN", "fake-token-de-teste")
os.environ.setdefault("DB_PATH", "/tmp/clutch-testes-moderacao.db")
os.environ.setdefault("LOG_LEVEL", "CRITICAL")

from cogs.moderacao import ErroDeHierarquia, Moderacao  # noqa: E402


class FakeRole:
    """Cargo com comparação por posição, como o discord.Role."""

    def __init__(self, position: int):
        self.position = position

    def __lt__(self, outro):
        return self.position < outro.position

    def __le__(self, outro):
        return self.position <= outro.position

    def __gt__(self, outro):
        return self.position > outro.position

    def __ge__(self, outro):
        return self.position >= outro.position


class FakeMember:
    """Membro com id, cargo mais alto e menção."""

    def __init__(self, member_id: int, posicao_cargo: int):
        self.id = member_id
        self.top_role = FakeRole(posicao_cargo)
        self.mention = f"<@{member_id}>"


ID_DONO = 1
ID_MOD = 2
ID_ALVO = 3
ID_BOT = 99


def montar_interacao(
    *,
    autor: FakeMember,
    posicao_bot: int = 50,
    owner_id: int = ID_DONO,
) -> SimpleNamespace:
    """Monta uma interação mínima para validar_alvo."""
    guild = SimpleNamespace(
        me=FakeMember(ID_BOT, posicao_bot),
        owner_id=owner_id,
    )
    return SimpleNamespace(user=autor, guild=guild)


class ValidarAlvoTests(unittest.TestCase):
    def test_caso_valido_nao_levanta(self) -> None:
        mod = FakeMember(ID_MOD, 40)
        alvo = FakeMember(ID_ALVO, 10)

        # Não deve levantar nada
        Moderacao.validar_alvo(montar_interacao(autor=mod), alvo, "banir")

    def test_nao_pune_a_si_mesmo(self) -> None:
        mod = FakeMember(ID_MOD, 40)

        with self.assertRaises(ErroDeHierarquia) as ctx:
            Moderacao.validar_alvo(montar_interacao(autor=mod), mod, "banir")

        self.assertIn("a si mesmo", str(ctx.exception))

    def test_nao_pune_o_bot(self) -> None:
        mod = FakeMember(ID_MOD, 40)
        interacao = montar_interacao(autor=mod)

        with self.assertRaises(ErroDeHierarquia):
            Moderacao.validar_alvo(interacao, interacao.guild.me, "banir")

    def test_nao_pune_o_dono_do_servidor(self) -> None:
        mod = FakeMember(ID_MOD, 40)
        dono = FakeMember(ID_DONO, 10)  # cargo baixo, mas é o dono

        with self.assertRaises(ErroDeHierarquia) as ctx:
            Moderacao.validar_alvo(montar_interacao(autor=mod), dono, "banir")

        self.assertIn("dono", str(ctx.exception))

    def test_nao_pune_cargo_igual(self) -> None:
        mod = FakeMember(ID_MOD, 40)
        alvo = FakeMember(ID_ALVO, 40)  # mesma posição

        with self.assertRaises(ErroDeHierarquia) as ctx:
            Moderacao.validar_alvo(montar_interacao(autor=mod), alvo, "expulsar")

        self.assertIn("igual ou superior", str(ctx.exception))

    def test_nao_pune_cargo_superior(self) -> None:
        mod = FakeMember(ID_MOD, 40)
        alvo = FakeMember(ID_ALVO, 41)

        with self.assertRaises(ErroDeHierarquia):
            Moderacao.validar_alvo(montar_interacao(autor=mod), alvo, "expulsar")

    def test_dono_do_servidor_ignora_hierarquia_de_cargo(self) -> None:
        dono = FakeMember(ID_DONO, 5)  # cargo baixo
        alvo = FakeMember(ID_ALVO, 40)  # cargo alto

        # O dono manda mesmo com cargo abaixo — mas o bot ainda precisa
        # estar acima do alvo, por isso posicao_bot=50
        Moderacao.validar_alvo(
            montar_interacao(autor=dono, posicao_bot=50), alvo, "banir"
        )

    def test_bot_abaixo_do_alvo_e_bloqueado(self) -> None:
        mod = FakeMember(ID_MOD, 90)
        alvo = FakeMember(ID_ALVO, 60)

        # Moderador está acima, mas o bot não: a API recusaria
        with self.assertRaises(ErroDeHierarquia) as ctx:
            Moderacao.validar_alvo(
                montar_interacao(autor=mod, posicao_bot=50), alvo, "banir"
            )

        self.assertIn("abaixo", str(ctx.exception))

    def test_dono_tambem_esbarra_no_cargo_do_bot(self) -> None:
        dono = FakeMember(ID_DONO, 5)
        alvo = FakeMember(ID_ALVO, 60)

        # Nem o dono do servidor faz o bot punir alguém acima dele
        with self.assertRaises(ErroDeHierarquia):
            Moderacao.validar_alvo(
                montar_interacao(autor=dono, posicao_bot=50), alvo, "banir"
            )


if __name__ == "__main__":
    unittest.main()

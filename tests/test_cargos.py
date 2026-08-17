"""
Testes da concessão de cargos por nível.

Cobre as regras que evitam erro 403 da API do Discord e cargos indevidos:
níveis já alcançados são concedidos retroativamente, cargos acima do bot são
ignorados, e nada é reatribuído se o membro já tem o cargo.
"""

import os
import unittest
from types import SimpleNamespace
from typing import List

os.environ.setdefault("DISCORD_TOKEN", "fake-token-de-teste")
os.environ.setdefault("DB_PATH", "/tmp/clutch-testes-cargos.db")
os.environ.setdefault("LOG_LEVEL", "CRITICAL")

import cogs.cargos as cargos_mod  # noqa: E402


class FakeRole:
    """Cargo comparável por posição."""

    def __init__(self, role_id: int, position: int, name: str = "cargo"):
        self.id = role_id
        self.position = position
        self.name = name

    def __ge__(self, outro):
        return self.position >= outro.position

    def __gt__(self, outro):
        return self.position > outro.position

    def __lt__(self, outro):
        return self.position < outro.position

    def __le__(self, outro):
        return self.position <= outro.position


class FakeGuild:
    """Servidor com um mapa de cargos e o cargo do bot."""

    def __init__(self, cargos: List[FakeRole], posicao_bot: int = 100):
        self.id = 777
        self._cargos = {c.id: c for c in cargos}
        self.me = SimpleNamespace(top_role=FakeRole(999, posicao_bot, "bot"))

    def get_role(self, role_id: int):
        return self._cargos.get(role_id)


class FakeMember:
    """Membro que registra os cargos recebidos."""

    def __init__(self, guild: FakeGuild, roles: List[FakeRole] = None):
        self.id = 42
        self.guild = guild
        self.roles = roles or []
        self.concedidos: List[FakeRole] = []
        self.falhar_com = None

    async def add_roles(self, *cargos, reason=None):
        if self.falhar_com:
            raise self.falhar_com
        self.concedidos.extend(cargos)


class ConcederCargosTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.recompensas = []
        # Substitui a consulta ao banco por dados controlados
        self._original = cargos_mod.listar_level_roles

        async def fake_listar(guild_id):
            return self.recompensas

        cargos_mod.listar_level_roles = fake_listar
        self.cog = cargos_mod.Cargos(bot=SimpleNamespace())

    def tearDown(self) -> None:
        cargos_mod.listar_level_roles = self._original

    async def test_sem_recompensas_nao_faz_nada(self) -> None:
        guild = FakeGuild([])
        membro = FakeMember(guild)

        self.assertEqual(await self.cog.conceder_cargos_de_nivel(membro, 10), [])
        self.assertEqual(membro.concedidos, [])

    async def test_concede_apenas_niveis_alcancados(self) -> None:
        cargo5 = FakeRole(1, 10, "Nível 5")
        cargo10 = FakeRole(2, 20, "Nível 10")
        guild = FakeGuild([cargo5, cargo10])
        membro = FakeMember(guild)

        self.recompensas = [
            {"level": 5, "role_id": 1},
            {"level": 10, "role_id": 2},
        ]

        concedidos = await self.cog.conceder_cargos_de_nivel(membro, 5)

        self.assertEqual([c.id for c in concedidos], [1])

    async def test_concede_retroativamente_niveis_pulados(self) -> None:
        cargos = [FakeRole(1, 10), FakeRole(2, 20), FakeRole(3, 30)]
        guild = FakeGuild(cargos)
        membro = FakeMember(guild)

        self.recompensas = [
            {"level": 1, "role_id": 1},
            {"level": 3, "role_id": 2},
            {"level": 5, "role_id": 3},
        ]

        # Quem chega direto ao nível 5 leva as três recompensas
        concedidos = await self.cog.conceder_cargos_de_nivel(membro, 5)

        self.assertEqual([c.id for c in concedidos], [1, 2, 3])

    async def test_nao_reatribui_cargo_que_ja_tem(self) -> None:
        cargo = FakeRole(1, 10)
        guild = FakeGuild([cargo])
        membro = FakeMember(guild, roles=[cargo])

        self.recompensas = [{"level": 1, "role_id": 1}]

        self.assertEqual(await self.cog.conceder_cargos_de_nivel(membro, 5), [])
        self.assertEqual(membro.concedidos, [])

    async def test_ignora_cargo_acima_do_bot(self) -> None:
        # position 150 > cargo do bot (100): a API recusaria
        alto = FakeRole(1, 150, "Admin")
        baixo = FakeRole(2, 10, "Membro")
        guild = FakeGuild([alto, baixo], posicao_bot=100)
        membro = FakeMember(guild)

        self.recompensas = [
            {"level": 1, "role_id": 1},
            {"level": 2, "role_id": 2},
        ]

        concedidos = await self.cog.conceder_cargos_de_nivel(membro, 5)

        self.assertEqual([c.id for c in concedidos], [2])

    async def test_ignora_cargo_apagado(self) -> None:
        guild = FakeGuild([])  # nenhum cargo existe mais
        membro = FakeMember(guild)

        self.recompensas = [{"level": 1, "role_id": 404}]

        self.assertEqual(await self.cog.conceder_cargos_de_nivel(membro, 5), [])

    async def test_falha_de_permissao_nao_propaga(self) -> None:
        import discord

        cargo = FakeRole(1, 10)
        guild = FakeGuild([cargo])
        membro = FakeMember(guild)
        membro.falhar_com = discord.Forbidden(
            SimpleNamespace(status=403, reason="Forbidden"), "sem permissão"
        )

        self.recompensas = [{"level": 1, "role_id": 1}]

        # Um level up não pode quebrar por causa de permissão de cargo
        self.assertEqual(await self.cog.conceder_cargos_de_nivel(membro, 5), [])


if __name__ == "__main__":
    unittest.main()

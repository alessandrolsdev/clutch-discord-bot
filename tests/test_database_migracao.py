"""
Testes de migração do schema e do cache de configuração por servidor.

Cobre o caso real de upgrade: um banco criado pela versão anterior tinha
``guild_config`` só com ``log_channel_id``. As colunas novas precisam ser
adicionadas sem perder os dados existentes.
"""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


class MigracaoTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "clutch.db"

        # Recria o schema ANTIGO, como estava na versão anterior do bot
        conexao = sqlite3.connect(self.db_path)
        conexao.executescript(
            """
            CREATE TABLE usuarios (
                id INTEGER PRIMARY KEY, nome TEXT, xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1, msg_count INTEGER DEFAULT 0,
                voice_minutes INTEGER DEFAULT 0, streak INTEGER DEFAULT 0,
                last_msg_date TEXT, bio TEXT
            );
            CREATE TABLE guild_config (
                guild_id INTEGER PRIMARY KEY,
                log_channel_id INTEGER
            );
            INSERT INTO usuarios (id, nome, xp, level) VALUES (123, 'antigo', 50, 2);
            INSERT INTO guild_config (guild_id, log_channel_id) VALUES (999, 555);
            """
        )
        conexao.commit()
        conexao.close()

        os.environ["DISCORD_TOKEN"] = "fake-token-de-teste"
        os.environ["DB_PATH"] = str(self.db_path)

        # Importa depois de definir DB_PATH: settings lê o ambiente no import
        import config.settings as settings_mod
        import importlib

        importlib.reload(settings_mod)

        import infra.database as db_mod

        importlib.reload(db_mod)
        self.db_mod = db_mod

        import utils.guild_config as gc_mod

        importlib.reload(gc_mod)
        self.gc_mod = gc_mod

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_migracao_preserva_dados_e_adiciona_colunas(self) -> None:
        await self.db_mod.inicializar_db()

        conexao = sqlite3.connect(self.db_path)
        colunas = {linha[1] for linha in conexao.execute("PRAGMA table_info(guild_config)")}

        # Colunas novas presentes
        for nova in ("levelup_channel_id", "xp_enabled", "autorole_id", "dj_role_id"):
            self.assertIn(nova, colunas)

        # Dados antigos intactos
        self.assertEqual(
            conexao.execute("SELECT log_channel_id FROM guild_config WHERE guild_id=999")
            .fetchone()[0],
            555,
        )
        self.assertEqual(
            conexao.execute("SELECT xp FROM usuarios WHERE id=123").fetchone()[0], 50
        )

        # Tabelas novas criadas
        tabelas = {
            linha[0]
            for linha in conexao.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for nova in ("level_roles", "warns", "xp_ignored_channels", "button_roles"):
            self.assertIn(nova, tabelas)

        conexao.close()

    async def test_migracao_e_idempotente(self) -> None:
        await self.db_mod.inicializar_db()
        await self.db_mod.inicializar_db()  # rodar de novo não pode falhar

        config = await self.db_mod.carregar_guild_config(999)
        self.assertEqual(config["log_channel_id"], 555)

    async def test_salvar_config_rejeita_campo_desconhecido(self) -> None:
        await self.db_mod.inicializar_db()

        # Barreira contra injeção via nome de coluna
        with self.assertRaises(ValueError):
            await self.db_mod.salvar_guild_config(999, coluna_maliciosa="x")

    async def test_warns_e_level_roles(self) -> None:
        await self.db_mod.inicializar_db()

        total = await self.db_mod.adicionar_warn(999, 42, 7, "spam")
        self.assertEqual(total, 1)
        total = await self.db_mod.adicionar_warn(999, 42, 7, "flood")
        self.assertEqual(total, 2)

        registros = await self.db_mod.listar_warns(999, 42)
        self.assertEqual(len(registros), 2)
        self.assertEqual(registros[0]["reason"], "flood")  # mais recente primeiro

        self.assertTrue(await self.db_mod.remover_warn(999, registros[0]["id"]))
        self.assertEqual(len(await self.db_mod.listar_warns(999, 42)), 1)

        self.assertEqual(await self.db_mod.limpar_warns(999, 42), 1)
        self.assertEqual(await self.db_mod.listar_warns(999, 42), [])

        await self.db_mod.definir_level_role(999, 5, 111)
        await self.db_mod.definir_level_role(999, 10, 222)
        # Redefinir o mesmo nível substitui em vez de duplicar
        await self.db_mod.definir_level_role(999, 5, 333)

        recompensas = await self.db_mod.listar_level_roles(999)
        self.assertEqual(recompensas, [{"level": 5, "role_id": 333}, {"level": 10, "role_id": 222}])

    async def test_canais_ignorados_alternam(self) -> None:
        await self.db_mod.inicializar_db()

        self.assertTrue(await self.db_mod.alternar_canal_ignorado(999, 777))
        self.assertEqual(await self.db_mod.listar_canais_ignorados(999), [777])

        self.assertFalse(await self.db_mod.alternar_canal_ignorado(999, 777))
        self.assertEqual(await self.db_mod.listar_canais_ignorados(999), [])


class CacheConfigTests(MigracaoTests):
    """Reaproveita o setUp da migração para testar o cache."""

    async def test_cache_evita_reconsulta_e_invalida_na_escrita(self) -> None:
        await self.db_mod.inicializar_db()

        cache = self.gc_mod.GuildConfigCache()

        config = await cache.obter(999)
        self.assertEqual(config.log_channel_id, 555)
        self.assertTrue(config.xp_enabled)  # padrão aplicado
        self.assertEqual(cache.tamanho, 1)

        # Segunda leitura vem do cache (mesmo objeto)
        self.assertIs(await cache.obter(999), config)

        # Escrita invalida e recarrega
        atualizado = await cache.atualizar(999, levelup_channel_id=888)
        self.assertEqual(atualizado.levelup_channel_id, 888)
        self.assertIsNot(atualizado, config)

    async def test_canal_ignorado_reflete_no_cache(self) -> None:
        await self.db_mod.inicializar_db()
        cache = self.gc_mod.GuildConfigCache()

        config = await cache.obter(999)
        self.assertTrue(config.da_xp_no_canal(777))

        await self.db_mod.alternar_canal_ignorado(999, 777)
        cache.invalidar(999)

        config = await cache.obter(999)
        self.assertFalse(config.da_xp_no_canal(777))

    async def test_xp_desligado_bloqueia_todos_os_canais(self) -> None:
        await self.db_mod.inicializar_db()
        cache = self.gc_mod.GuildConfigCache()

        await cache.atualizar(999, xp_enabled=0)
        config = await cache.obter(999)

        self.assertFalse(config.da_xp_no_canal(123456))


if __name__ == "__main__":
    unittest.main()

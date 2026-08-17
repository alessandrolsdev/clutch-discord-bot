"""
Testes do backup do banco.

O ponto central: o backup precisa ser consistente mesmo com WAL ligado —
copiar só o arquivo .db com o WAL pendente perde as escritas recentes.
"""

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("DISCORD_TOKEN", "fake-token-de-teste")
os.environ.setdefault("LOG_LEVEL", "CRITICAL")

from infra.backup import (  # noqa: E402
    criar_backup,
    limpar_antigos,
    listar_backups,
    restaurar_backup,
)


class BackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self._tmp.name)
        self.db = self.raiz / "clutch.db"
        self.backups = self.raiz / "backups"

        conexao = sqlite3.connect(self.db)
        conexao.execute("PRAGMA journal_mode=WAL")
        conexao.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, nome TEXT)")
        conexao.execute("INSERT INTO usuarios VALUES (1, 'zibras')")
        conexao.commit()
        self.conexao = conexao  # mantém aberta: simula o bot rodando

    def tearDown(self) -> None:
        self.conexao.close()
        self._tmp.cleanup()

    def test_backup_captura_dados_com_wal_pendente(self) -> None:
        # Escrita commitada mas ainda no WAL, com a conexão aberta
        self.conexao.execute("INSERT INTO usuarios VALUES (2, 'trataker')")
        self.conexao.commit()

        destino = criar_backup(self.db, self.backups)

        self.assertIsNotNone(destino)
        self.assertTrue(destino.is_file())

        copia = sqlite3.connect(destino)
        nomes = {linha[0] for linha in copia.execute("SELECT nome FROM usuarios")}
        copia.close()

        # Se o backup fosse um `cp` simples, 'trataker' poderia faltar
        self.assertEqual(nomes, {"zibras", "trataker"})

    def test_banco_inexistente_retorna_none(self) -> None:
        self.assertIsNone(criar_backup(self.raiz / "nao-existe.db", self.backups))

    def test_cria_diretorio_de_destino(self) -> None:
        self.assertFalse(self.backups.exists())
        criar_backup(self.db, self.backups)
        self.assertTrue(self.backups.is_dir())

    def test_rotacao_mantem_os_mais_recentes(self) -> None:
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        for dia in range(5):
            criar_backup(self.db, self.backups, manter=3, momento=base + timedelta(days=dia))

        arquivos = listar_backups(self.backups)
        self.assertEqual(len(arquivos), 3)

        # Os preservados são os três últimos (nome carrega a data)
        self.assertEqual(arquivos[0].name, "clutch-backup-20260105-120000.db")
        self.assertEqual(arquivos[-1].name, "clutch-backup-20260103-120000.db")

    def test_listar_ordena_do_mais_recente_para_o_mais_antigo(self) -> None:
        base = datetime(2026, 3, 1, 8, 0, 0, tzinfo=timezone.utc)
        for hora in range(3):
            criar_backup(self.db, self.backups, momento=base + timedelta(hours=hora))

        nomes = [a.name for a in listar_backups(self.backups)]
        self.assertEqual(nomes, sorted(nomes, reverse=True))

    def test_listar_ignora_arquivos_estranhos(self) -> None:
        self.backups.mkdir()
        (self.backups / "anotacoes.txt").write_text("nada a ver")
        (self.backups / "outro.db").write_bytes(b"")

        criar_backup(self.db, self.backups)

        arquivos = listar_backups(self.backups)
        self.assertEqual(len(arquivos), 1)
        self.assertTrue(arquivos[0].name.startswith("clutch-backup-"))

    def test_limpar_antigos_com_manter_zero_nao_apaga(self) -> None:
        criar_backup(self.db, self.backups)
        # manter<1 é tratado como "não mexer", em vez de apagar tudo
        self.assertEqual(limpar_antigos(self.backups, 0), 0)
        self.assertEqual(len(listar_backups(self.backups)), 1)

    def test_restaurar_recupera_os_dados_e_guarda_o_anterior(self) -> None:
        destino = criar_backup(self.db, self.backups)

        # Estraga o banco depois do backup
        self.conexao.execute("DELETE FROM usuarios")
        self.conexao.commit()
        self.conexao.close()

        self.assertTrue(restaurar_backup(destino, self.db))

        conexao = sqlite3.connect(self.db)
        total = conexao.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        conexao.close()

        self.assertEqual(total, 1)
        self.assertTrue(self.db.with_suffix(".antes-da-restauracao").is_file())

        self.conexao = sqlite3.connect(self.db)  # para o tearDown

    def test_restaurar_backup_inexistente_falha(self) -> None:
        self.assertFalse(restaurar_backup(self.raiz / "nada.db", self.db))


if __name__ == "__main__":
    unittest.main()

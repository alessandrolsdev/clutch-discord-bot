#!/usr/bin/env python3
"""
VERIFICADOR DE COGS
===================

Carrega todas as extensões contra um bot que nunca conecta ao Discord e
reporta falhas de import, erros de registro e nomes de comando duplicados.

Existe porque dois erros reais só aparecem no momento do carregamento e
passariam por qualquer teste unitário:
- dois app commands com o mesmo nome levantam ``CommandAlreadyRegistered``
  e impedem um cog inteiro de carregar;
- uma dependência ausente no requirements.txt só falha no import.

Uso:
    python scripts/verificar_cogs.py

Saída: código 0 se tudo carregou e não há nomes duplicados.
"""

import asyncio
import os
import sys
from collections import Counter
from pathlib import Path

# Permite rodar de qualquer diretório
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# config/settings.py exige DISCORD_TOKEN já no import
os.environ.setdefault("DISCORD_TOKEN", "token-falso-para-verificacao")
os.environ.setdefault("DB_PATH", "/tmp/verificar-cogs.db")
os.environ.setdefault("LOG_LEVEL", "CRITICAL")
# Não tenta subir a API HTTP durante a verificação
os.environ.setdefault("API_PORT", "0")

from main import COGS_DIR, ClutchBot  # noqa: E402


def _silenciar_loops_offline(loop: asyncio.AbstractEventLoop) -> None:
    """
    Ignora o erro esperado dos tasks.loop num bot que nunca conecta.

    Cogs com loop periódico chamam ``wait_until_ready()`` no ``before_loop``,
    que levanta RuntimeError quando o bot não fez login. Aqui isso é esperado —
    qualquer outro erro continua sendo reportado.
    """

    def handler(_loop, contexto):
        excecao = contexto.get("exception")
        if isinstance(excecao, RuntimeError) and "not been properly initialised" in str(
            excecao
        ):
            return
        print(f"  ⚠️  Erro assíncrono: {contexto.get('message')} {excecao!r}")

    loop.set_exception_handler(handler)


async def verificar() -> int:
    """Carrega os cogs e valida a árvore de comandos."""
    _silenciar_loops_offline(asyncio.get_running_loop())

    bot = ClutchBot()
    falhas: list[tuple[str, str]] = []
    carregados = 0

    for arquivo in sorted(COGS_DIR.glob("*.py")):
        if arquivo.name == "__init__.py":
            continue

        try:
            await bot.load_extension(f"cogs.{arquivo.stem}")
            print(f"  ✅ {arquivo.name}")
            carregados += 1
        except Exception as e:  # noqa: BLE001 - queremos reportar qualquer falha
            print(f"  ❌ {arquivo.name}: {e!r}")
            falhas.append((arquivo.name, repr(e)))

    nomes = [comando.name for comando in bot.tree.get_commands()]
    duplicados = [nome for nome, total in Counter(nomes).items() if total > 1]

    print(f"\nCogs carregados: {carregados}")
    print(f"Slash commands: {len(nomes)}")

    if duplicados:
        print(f"❌ Nomes duplicados: {duplicados}")

    # Descarrega antes de fechar: os cogs com tasks.loop cancelam seus loops
    # no cog_unload. Sem isso os loops falham em wait_until_ready (o bot nunca
    # conectou) e poluem a saída do CI com tracebacks irrelevantes.
    for extensao in list(bot.extensions):
        try:
            await bot.unload_extension(extensao)
        except Exception:
            pass

    await bot.close()

    if falhas or duplicados:
        print("\n❌ Verificação falhou.")
        return 1

    print("\n✅ Todos os cogs carregaram sem conflito de nomes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(verificar()))

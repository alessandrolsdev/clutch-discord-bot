"""
CLUTCH BOT - CLIENTE DE IA (GOOGLE GEMINI)
==========================================

Centraliza o acesso ao Gemini para os cogs.

Por que existe:
- ``model.generate_content()`` é uma chamada HTTP **síncrona**. Chamada direto
  dentro de um handler async, ela congela o event loop inteiro do bot (voz,
  comandos e heartbeat do gateway) por segundos. Aqui ela roda numa thread.
- Cada cog configurava a API key e o nome do modelo por conta própria, com
  valores divergentes. Agora tudo vem de ``config.settings``.
- ``response.text`` levanta exceção quando a resposta é bloqueada por filtro de
  segurança ou vem vazia; isso é tratado num lugar só.
"""

import asyncio
from typing import Optional

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - dependência opcional em dev/testes
    genai = None


# Limite do Discord para descrição de embed
MAX_EMBED_DESCRIPTION = 4096


class GeminiClient:
    """Wrapper assíncrono e tolerante a falhas em cima do Google Gemini."""

    def __init__(self) -> None:
        self.model_name = settings.ai.model_name
        self._api_key = settings.ai.api_key
        self._configured = False

        if self.is_enabled:
            genai.configure(api_key=self._api_key)
            self._configured = True
        elif not self._api_key:
            logger.warning(
                "GEMINI_API_KEY não configurado — comandos de IA ficarão indisponíveis."
            )
        else:
            logger.warning(
                "google-generativeai não instalado — comandos de IA ficarão indisponíveis."
            )

    @property
    def is_enabled(self) -> bool:
        """True se há API key e a biblioteca está disponível."""
        return bool(self._api_key) and genai is not None

    def _gerar_sync(self, prompt: str) -> Optional[str]:
        """Chamada bloqueante ao Gemini (executada fora do event loop)."""
        model = genai.GenerativeModel(
            self.model_name,
            generation_config={
                "temperature": settings.ai.temperature,
                "max_output_tokens": settings.ai.max_tokens,
            },
        )
        response = model.generate_content(prompt)

        # .text levanta ValueError quando a resposta foi bloqueada/vazia
        try:
            texto = response.text
        except (ValueError, AttributeError):
            logger.warning("Resposta do Gemini sem texto utilizável (filtro/vazia).")
            return None

        texto = (texto or "").strip()
        return texto or None

    async def gerar(self, prompt: str) -> Optional[str]:
        """
        Gera texto a partir de um prompt, sem bloquear o event loop.

        Args:
            prompt: Prompt completo enviado ao modelo

        Returns:
            Texto gerado, ou None se a IA está desabilitada ou falhou
        """
        if not self.is_enabled or not self._configured:
            return None

        try:
            texto = await asyncio.to_thread(self._gerar_sync, prompt)
        except Exception as e:
            logger.error("Falha ao gerar conteúdo no Gemini: %s", e, exc_info=True)
            return None

        if texto and len(texto) > MAX_EMBED_DESCRIPTION:
            texto = texto[: MAX_EMBED_DESCRIPTION - 1] + "…"

        return texto


# Instância compartilhada por todos os cogs
gemini = GeminiClient()

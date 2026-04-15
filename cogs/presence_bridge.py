import asyncio
from typing import Any, Optional

import discord
from discord.ext import commands

from config.settings import settings
from utils.logger import get_logger
from utils.presence_bridge import (
    ClutchPresenceClient,
    PresenceDeduplicator,
    build_presence_payload,
    should_process_member,
)

logger = get_logger(__name__)


class PresenceBridge(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = settings.presence_bridge
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        self.deduplicator = PresenceDeduplicator(self.config.dedup_seconds)
        self.client = ClutchPresenceClient(
            base_url=self.config.api_base_url,
            ingest_token=self.config.ingest_token,
            dry_run=self.config.dry_run,
            request_timeout_seconds=self.config.request_timeout_seconds,
            logger=logger,
        )
        self.worker_task: Optional[asyncio.Task[None]] = None

        if self.client.is_enabled:
            logger.info(
                "Discord presence bridge inicializada dry_run=%s target_guild_id=%s dedup_seconds=%s",
                self.config.dry_run,
                self.config.target_guild_id,
                self.config.dedup_seconds,
            )
        else:
            logger.warning(
                "Discord presence bridge desabilitada: defina CLUTCH_API_BASE_URL e CLUTCH_DISCORD_INGEST_TOKEN ou habilite CLUTCH_PRESENCE_DRY_RUN"
            )

    async def cog_load(self) -> None:
        self.worker_task = asyncio.create_task(
            self._worker_loop(),
            name="clutch-discord-presence-bridge",
        )

    def cog_unload(self) -> None:
        if self.worker_task:
            self.worker_task.cancel()
        self.bot.loop.create_task(self.client.close())

    @commands.Cog.listener()
    async def on_presence_update(
        self,
        before: discord.Member,
        after: discord.Member,
    ) -> None:
        if not self.client.is_enabled:
            return

        if not should_process_member(after, self.config.target_guild_id):
            logger.debug(
                "Discord presence bridge ignorou membro externalId=%s guildId=%s",
                getattr(after, "id", None),
                getattr(getattr(after, "guild", None), "id", None),
            )
            return

        payload = build_presence_payload(after)
        if self.deduplicator.should_skip(payload):
            logger.info(
                "Discord presence bridge descartou evento duplicado externalId=%s status=%s guildId=%s",
                payload.get("externalId"),
                payload.get("status"),
                getattr(getattr(after, "guild", None), "id", None),
            )
            return

        try:
            self.queue.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning(
                "Discord presence bridge descartou payload por fila cheia externalId=%s guildId=%s",
                payload.get("externalId"),
                getattr(getattr(after, "guild", None), "id", None),
            )

    async def _worker_loop(self) -> None:
        while True:
            payload = await self.queue.get()
            try:
                await self.client.send(payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Discord presence bridge falhou com erro inesperado externalId=%s error=%s",
                    payload.get("externalId"),
                    exc,
                    exc_info=True,
                )
            finally:
                self.queue.task_done()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PresenceBridge(bot))

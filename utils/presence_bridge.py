import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

try:
    import aiohttp
except ModuleNotFoundError:  # pragma: no cover - fallback para testes sem deps
    aiohttp = None

RETRYABLE_STATUSES = {408, 425, 429, 500, 502, 503, 504}
SleepFunc = Callable[[float], Awaitable[None]]


def _enum_name(value: Any) -> Optional[str]:
    candidate = getattr(value, "name", value)
    if candidate is None:
        return None
    return str(candidate).strip().lower()


def _select_primary_activity(activities: list[Any]) -> Any | None:
    for activity in activities:
        activity_type = _enum_name(getattr(activity, "type", None))
        if activity_type == "playing" and getattr(activity, "name", None):
            return activity
    return None


def _build_game_details(activity: Any | None) -> dict[str, Any] | None:
    if activity is None:
        return None

    payload: dict[str, Any] = {
        "source": "DISCORD",
        "activityType": (_enum_name(getattr(activity, "type", None)) or "unknown").upper(),
    }

    details = getattr(activity, "details", None)
    state = getattr(activity, "state", None)

    if isinstance(details, str) and details.strip():
        payload["details"] = details.strip()
    if isinstance(state, str) and state.strip():
        payload["state"] = state.strip()

    return payload


def _normalize_status(status_name: Optional[str], current_game: Optional[str]) -> str:
    if current_game:
        return "IN_GAME"
    if status_name == "idle":
        return "AFK"
    if status_name in {"online", "dnd", "do_not_disturb"}:
        return "ONLINE"
    return "OFFLINE"


def should_process_member(member: Any, target_guild_id: Optional[int]) -> bool:
    if getattr(member, "bot", False):
        return False

    if target_guild_id is None:
        return True

    guild = getattr(member, "guild", None)
    guild_id = getattr(guild, "id", None)
    return guild_id == target_guild_id


def build_presence_payload(member: Any, observed_at: Optional[str] = None) -> dict[str, Any]:
    activities = list(getattr(member, "activities", []) or [])
    primary_activity = _select_primary_activity(activities)
    current_game = getattr(primary_activity, "name", None)

    return {
        "externalId": str(member.id),
        "status": _normalize_status(_enum_name(getattr(member, "status", None)), current_game),
        "currentGame": current_game,
        "gameDetails": _build_game_details(primary_activity),
    }


@dataclass
class PresenceDeduplicator:
    ttl_seconds: int

    def __post_init__(self) -> None:
        self._cache: dict[str, tuple[str, float]] = {}

    def should_skip(self, payload: dict[str, Any], now: Optional[float] = None) -> bool:
        if self.ttl_seconds <= 0:
            return False

        current_time = time.monotonic() if now is None else now
        self._prune(current_time)

        member_key = str(payload["externalId"])
        signature = json.dumps(
            {
                "status": payload.get("status"),
                "currentGame": payload.get("currentGame"),
                "gameDetails": payload.get("gameDetails"),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        cached = self._cache.get(member_key)
        if cached and cached[0] == signature and cached[1] > current_time:
            return True

        self._cache[member_key] = (signature, current_time + self.ttl_seconds)
        return False

    def _prune(self, now: float) -> None:
        expired_keys = [
            cache_key
            for cache_key, (_, expires_at) in self._cache.items()
            if expires_at <= now
        ]
        for cache_key in expired_keys:
            self._cache.pop(cache_key, None)


class ClutchPresenceClient:
    def __init__(
        self,
        *,
        base_url: Optional[str],
        ingest_token: Optional[str],
        dry_run: bool,
        request_timeout_seconds: float,
        session: Any = None,
        logger: Optional[logging.Logger] = None,
        sleep_func: SleepFunc = asyncio.sleep,
        max_attempts: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.ingest_token = ingest_token
        self.dry_run = dry_run
        self.request_timeout_seconds = request_timeout_seconds
        self.logger = logger or logging.getLogger(__name__)
        self._session = session
        self._owns_session = session is None
        self._sleep_func = sleep_func
        self._max_attempts = max_attempts

    @property
    def is_enabled(self) -> bool:
        return self.dry_run or bool(self.base_url and self.ingest_token)

    @property
    def endpoint_url(self) -> Optional[str]:
        if not self.base_url:
            return None
        return f"{self.base_url}/integrations/discord/presence"

    async def send(self, payload: dict[str, Any]) -> bool:
        if self.dry_run:
            self.logger.info(
                "Discord presence bridge dry-run payload=%s",
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            )
            return True

        if not self.endpoint_url or not self.ingest_token:
            self.logger.warning(
                "Discord presence bridge sem configuração; externalId=%s descartado",
                payload.get("externalId"),
            )
            return False

        headers = {
            "Content-Type": "application/json",
            "x-clutch-discord-ingest-token": self.ingest_token,
        }
        timeout = (
            aiohttp.ClientTimeout(total=self.request_timeout_seconds)
            if aiohttp is not None
            else self.request_timeout_seconds
        )

        for attempt in range(1, self._max_attempts + 1):
            try:
                session = await self._get_session()
                async with session.post(
                    self.endpoint_url,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                ) as response:
                    response_text = await response.text()
                    if 200 <= response.status < 300:
                        self.logger.info(
                            "Discord presence bridge enviou payload externalId=%s status=%s http=%s",
                            payload.get("externalId"),
                            payload.get("status"),
                            response.status,
                        )
                        return True

                    is_retryable = response.status in RETRYABLE_STATUSES
                    log_method = self.logger.warning if is_retryable else self.logger.error
                    log_method(
                        "Discord presence bridge falhou externalId=%s status=%s http=%s attempt=%s body=%s",
                        payload.get("externalId"),
                        payload.get("status"),
                        response.status,
                        attempt,
                        self._truncate(response_text),
                    )
                    if not is_retryable or attempt == self._max_attempts:
                        return False
            except self._request_exceptions() as exc:
                log_method = self.logger.warning if attempt < self._max_attempts else self.logger.error
                log_method(
                    "Discord presence bridge erro de rede externalId=%s status=%s attempt=%s error=%s",
                    payload.get("externalId"),
                    payload.get("status"),
                    attempt,
                    exc,
                )
                if attempt == self._max_attempts:
                    return False

            await self._sleep_func(0.5 * attempt)

        return False

    async def close(self) -> None:
        if self._owns_session and self._session and not getattr(self._session, "closed", False):
            await self._session.close()

    async def _get_session(self) -> Any:
        if self._session is None or getattr(self._session, "closed", False):
            if aiohttp is None:
                raise RuntimeError(
                    "aiohttp não está instalado; não é possível criar sessão HTTP real"
                )
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    @staticmethod
    def _request_exceptions() -> tuple[type[BaseException], ...]:
        if aiohttp is None:
            return (asyncio.TimeoutError, RuntimeError)
        return (aiohttp.ClientError, asyncio.TimeoutError)

    @staticmethod
    def _truncate(value: str, limit: int = 300) -> str:
        sanitized = value.strip().replace("\n", " ")
        if len(sanitized) <= limit:
            return sanitized
        return f"{sanitized[:limit]}..."

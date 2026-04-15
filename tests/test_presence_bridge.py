import unittest
from types import SimpleNamespace

from utils.presence_bridge import (
    ClutchPresenceClient,
    PresenceDeduplicator,
    build_presence_payload,
    should_process_member,
)


def enum_like(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


class FakeActivity:
    def __init__(
        self,
        type_name: str,
        name: str | None = None,
        details: str | None = None,
        state: str | None = None,
    ) -> None:
        self.type = enum_like(type_name)
        self.name = name
        self.details = details
        self.state = state


class FakeMember:
    def __init__(
        self,
        *,
        member_id: int = 42,
        guild_id: int = 7,
        bot: bool = False,
        status: str = "online",
        activities: list[FakeActivity] | None = None,
        desktop_status: str = "offline",
        mobile_status: str = "offline",
        web_status: str = "offline",
    ) -> None:
        self.id = member_id
        self.bot = bot
        self.guild = SimpleNamespace(id=guild_id)
        self.status = enum_like(status)
        self.activities = activities or []
        self.desktop_status = enum_like(desktop_status)
        self.mobile_status = enum_like(mobile_status)
        self.web_status = enum_like(web_status)


class FakeResponse:
    def __init__(self, status: int, text: str = "") -> None:
        self.status = status
        self._text = text

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def text(self) -> str:
        return self._text


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.closed = False

    def post(self, url: str, *, json: dict, headers: dict, timeout) -> FakeResponse:
        self.calls.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return self.responses.pop(0)

    async def close(self) -> None:
        self.closed = True


async def no_sleep(_: float) -> None:
    return None


class PresencePayloadTests(unittest.TestCase):
    def test_build_payload_maps_playing_activity_to_in_game(self) -> None:
        member = FakeMember(
            status="online",
            activities=[
                FakeActivity(
                    "playing",
                    name="VALORANT",
                    details="Competitive",
                    state="Ascent",
                )
            ],
            desktop_status="online",
        )

        payload = build_presence_payload(member, observed_at="2026-04-15T03:10:22Z")

        self.assertEqual(
            payload,
            {
                "externalId": "42",
                "status": "IN_GAME",
                "currentGame": "VALORANT",
                "gameDetails": {
                    "source": "DISCORD",
                    "activityType": "PLAYING",
                    "details": "Competitive",
                    "state": "Ascent",
                },
            },
        )

    def test_build_payload_maps_idle_without_game_to_afk(self) -> None:
        member = FakeMember(status="idle", mobile_status="online")

        payload = build_presence_payload(member, observed_at="2026-04-15T03:10:22Z")

        self.assertEqual(payload["status"], "AFK")
        self.assertIsNone(payload["currentGame"])
        self.assertIsNone(payload["gameDetails"])

    def test_should_process_member_ignores_bots_and_other_guilds(self) -> None:
        bot_member = FakeMember(bot=True)
        other_guild_member = FakeMember(guild_id=999)
        allowed_member = FakeMember(guild_id=7)

        self.assertFalse(should_process_member(bot_member, target_guild_id=None))
        self.assertFalse(should_process_member(other_guild_member, target_guild_id=7))
        self.assertTrue(should_process_member(allowed_member, target_guild_id=7))

    def test_deduplicator_skips_equivalent_payloads_inside_ttl(self) -> None:
        deduplicator = PresenceDeduplicator(ttl_seconds=30)
        payload = {
            "externalId": "42",
            "status": "ONLINE",
            "currentGame": None,
            "gameDetails": None,
        }

        self.assertFalse(deduplicator.should_skip(payload, now=100.0))
        self.assertTrue(deduplicator.should_skip(payload, now=110.0))
        self.assertFalse(
            deduplicator.should_skip(
                {**payload, "status": "AFK"},
                now=115.0,
            )
        )
        self.assertFalse(deduplicator.should_skip(payload, now=150.0))


class PresenceClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_does_not_send_post(self) -> None:
        session = FakeSession([FakeResponse(200)])
        client = ClutchPresenceClient(
            base_url="http://127.0.0.1:8080",
            ingest_token="secret-token",
            dry_run=True,
            request_timeout_seconds=2.0,
            session=session,
            sleep_func=no_sleep,
        )

        sent = await client.send(
            {
                "externalId": "42",
                "status": "ONLINE",
                "currentGame": None,
                "gameDetails": None,
            }
        )

        self.assertTrue(sent)
        self.assertEqual(session.calls, [])

    async def test_client_retries_until_success(self) -> None:
        session = FakeSession(
            [
                FakeResponse(503, "upstream unavailable"),
                FakeResponse(200, '{"message":"ok"}'),
            ]
        )
        client = ClutchPresenceClient(
            base_url="http://127.0.0.1:8080",
            ingest_token="secret-token",
            dry_run=False,
            request_timeout_seconds=2.0,
            session=session,
            sleep_func=no_sleep,
        )

        sent = await client.send(
            {
                "externalId": "42",
                "status": "IN_GAME",
                "currentGame": "VALORANT",
                "gameDetails": {"source": "DISCORD", "activityType": "PLAYING"},
            }
        )

        self.assertTrue(sent)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(
            session.calls[0]["url"],
            "http://127.0.0.1:8080/integrations/discord/presence",
        )
        self.assertEqual(
            session.calls[0]["headers"]["x-clutch-discord-ingest-token"],
            "secret-token",
        )

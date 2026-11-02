from pathlib import Path

import aiohttp
import pytest
from aiohttp import web

from vklass import (
    Child,
    VklassAuthError,
    VklassClient,
    VklassConnectionError,
    VklassError,
    VklassParseError,
)

FIXTURES = Path(__file__).parent / "fixtures"
KID = Child("kid", "Alva")


class Fake:
    """Stands in for cal.vklass.se (/feed) and skolmaten.se (/lunch)."""

    def __init__(self):
        self.feed = (FIXTURES / "feed.ics").read_text(encoding="utf-8")
        self.feed_status = 200
        self.lunch = (FIXTURES / "lunch.xml").read_text(encoding="utf-8")
        self.lunch_status = 200
        self.requests = []

    def app(self):
        app = web.Application()
        app.router.add_get("/feed", self.serve_feed)
        app.router.add_get("/lunch", self.serve_lunch)
        return app

    async def serve_feed(self, request):
        self.requests.append(request.headers.get("Accept"))
        return web.Response(
            text=self.feed, status=self.feed_status, content_type="text/calendar"
        )

    async def serve_lunch(self, request):
        return web.Response(text=self.lunch, status=self.lunch_status)


@pytest.fixture
async def fake(aiohttp_client):
    f = Fake()
    http = await aiohttp_client(f.app())
    f.session = http.session
    f.feed_url = str(http.make_url("/feed"))
    f.lunch_url = str(http.make_url("/lunch"))
    return f


def client(fake, lunch=False):
    return VklassClient(
        fake.session,
        fake.feed_url,
        lunch_url=fake.lunch_url if lunch else None,
    )


async def test_get_events(fake):
    events = await client(fake).get_events(KID)
    assert len(events) == 8
    assert {e.child_id for e in events} == {"kid"}
    assert fake.requests == ["text/calendar"]


async def test_unknown_link_answers_empty_200(fake):
    fake.feed = ""
    with pytest.raises(VklassAuthError):
        await client(fake).get_events(KID)


async def test_404_means_link_not_recognised(fake):
    fake.feed_status = 404
    with pytest.raises(VklassAuthError):
        await client(fake).get_events(KID)


async def test_bot_protection_is_a_connection_error_not_an_auth_error(fake):
    fake.feed_status = 403
    with pytest.raises(VklassConnectionError):
        await client(fake).get_events(KID)
    fake.feed_status = 200
    fake.feed = "<html><title>Verifying...</title></html>"
    with pytest.raises(VklassConnectionError):
        await client(fake).get_events(KID)


async def test_server_error(fake):
    fake.feed_status = 500
    with pytest.raises(VklassConnectionError):
        await client(fake).get_events(KID)


async def test_unreachable():
    async with aiohttp.ClientSession() as session:
        c = VklassClient(session, "http://127.0.0.1:1/feed")
        with pytest.raises(VklassConnectionError):
            await c.get_events(KID)


async def test_lunches(fake):
    lunches = await client(fake, lunch=True).get_lunches()
    assert [l.date.isoformat() for l in lunches] == ["2026-11-02", "2026-11-03"]


async def test_no_lunch_link_means_no_lunches(fake):
    assert await client(fake).get_lunches() == []


async def test_lunch_errors_are_vklass_errors(fake):
    fake.lunch_status = 404
    with pytest.raises(VklassError):
        await client(fake, lunch=True).get_lunches()
    fake.lunch_status = 200
    fake.lunch = "<html>oops</html>"
    with pytest.raises(VklassParseError):
        await client(fake, lunch=True).get_lunches()

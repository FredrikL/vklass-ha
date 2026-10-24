from datetime import date
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web

from vklass import (
    Child,
    VklassAuthError,
    VklassClient,
    VklassConnectionError,
    VklassParseError,
)

FIXTURES = Path(__file__).parent / "fixtures"
ALVA = Child(1001, "Alva")


class FakeVklass:
    """Stands in for both auth.vklass.se (/auth) and custodian.vklass.se (/c)."""

    def __init__(self):
        self.logins = 0
        self.valid_sessions = set()
        self.calendar_posts = []
        self.calendar_body = (FIXTURES / "calendar.json").read_text(encoding="utf-8")

    def app(self):
        app = web.Application()
        app.router.add_get("/auth/credentials", self.credentials)
        app.router.add_post("/auth/credentials/signin", self.signin)
        app.router.add_get("/auth/process", self.process)
        app.router.add_get("/c/landing", self.landing)
        app.router.add_get("/c/Calendar/Schedule/", self.schedule)
        app.router.add_get("/c/Home/Welcome", self.welcome)
        app.router.add_post("/c/Events/FullCalendar", self.calendar)
        return app

    async def credentials(self, request):
        return web.Response(text=(FIXTURES / "login.html").read_text())

    async def signin(self, request):
        form = await request.post()
        if (
            form["__RequestVerificationToken"] != "tok-123"
            or form["Username"] != "guardian"
            or form["Password"] != "secret"
        ):
            return web.Response(text="form again")
        self.logins += 1
        sid = f"s{self.logins}"
        self.valid_sessions.add(sid)
        resp = web.Response(status=302, headers={"Location": "/auth/process"})
        resp.set_cookie("sid", sid)
        # Vklass clears cookies like this on sign-in; naive jars keep them.
        resp.headers.add(
            "Set-Cookie", "stale=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/"
        )
        return resp

    async def process(self, request):
        # The real /process answers 403 when a cleared cookie is sent back.
        if "stale" in request.cookies:
            return web.Response(status=403)
        return web.Response(status=302, headers={"Location": "/c/landing"})

    async def landing(self, request):
        return web.Response(text="welcome")

    def _authed(self, request):
        return request.cookies.get("sid") in self.valid_sessions

    def _expired(self):
        return web.Response(status=302, headers={"Location": "/auth/credentials"})

    async def schedule(self, request):
        if not self._authed(request):
            return self._expired()
        return web.Response(text=(FIXTURES / "schedule.html").read_text())

    async def welcome(self, request):
        if not self._authed(request):
            return self._expired()
        return web.Response(text=(FIXTURES / "welcome.html").read_text())

    async def calendar(self, request):
        if not self._authed(request):
            return self._expired()
        self.calendar_posts.append(dict(await request.post()))
        return web.Response(text=self.calendar_body, content_type="application/json")


@pytest.fixture
async def env(aiohttp_server):
    fake = FakeVklass()
    server = await aiohttp_server(fake.app())
    base = f"http://{server.host}:{server.port}"
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True)
    ) as session:

        def make(password="secret"):
            return VklassClient(
                session,
                "guardian",
                password,
                auth_url=f"{base}/auth",
                base_url=f"{base}/c",
            )

        yield fake, make


async def test_bad_credentials(env):
    _, make = env
    with pytest.raises(VklassAuthError):
        await make("wrong").login()


async def test_lazy_login_and_children(env):
    fake, make = env
    client = make()
    assert fake.logins == 0
    assert await client.get_children() == [ALVA, Child(1002, "Bo")]
    assert fake.logins == 1


async def test_events_request_and_result(env):
    fake, make = env
    events = await make().get_upcoming_events(ALVA, days=7, today=date(2026, 10, 19))
    assert len(events) == 5
    assert fake.calendar_posts == [
        {
            "students": "1001",
            "start": "2026-10-19T00:00:00",
            "end": "2026-10-26T00:00:00",
        }
    ]


async def test_lunches_per_child(env):
    _, make = env
    children = [ALVA, Child(1002, "Bo"), Child(1003, "Nobody")]
    lunches = await make().get_lunches(children, today=date(2026, 10, 22))
    assert [(l.date, l.dishes) for l in lunches[1001]] == [
        (date(2026, 10, 22), ["Köttbullar med potatis", "Vegetariskt: Linsgryta"]),
        (date(2026, 10, 23), ["Fiskgratäng"]),
        (date(2026, 10, 27), ["Pannkakor & sylt"]),
    ]
    assert [(l.date, l.dishes) for l in lunches[1002]] == [
        (date(2026, 10, 22), ["Köttbullar med potatis"])
    ]
    assert lunches[1003] == []


async def test_relogin_when_session_expires(env):
    fake, make = env
    client = make()
    await client.get_children()
    fake.valid_sessions.clear()  # server forgets us
    assert await client.get_children()
    assert fake.logins == 2


async def test_session_rejected_after_relogin(env):
    fake, make = env
    client = make()
    await client.get_children()
    fake._authed = lambda request: False  # server never accepts our cookie
    with pytest.raises(VklassAuthError):
        await client.get_children()
    assert fake.logins == 2  # logged in once more, then gave up


async def test_non_json_calendar(env):
    fake, make = env
    fake.calendar_body = "<html>oops</html>"
    with pytest.raises(VklassParseError):
        await make().get_events(ALVA, *_range())


async def test_connection_error():
    async with aiohttp.ClientSession() as session:
        client = VklassClient(
            session, "u", "p", auth_url="http://127.0.0.1:1", base_url="http://127.0.0.1:1"
        )
        with pytest.raises(VklassConnectionError):
            await client.login()


def _range():
    from datetime import datetime

    return datetime(2026, 10, 19), datetime(2026, 10, 26)

# Vklass guardian API notes

Observed 2026-10-23 against custodian.vklass.se as a guardian account. No public API;
the guardian UI is an Aurelia SPA (hash routes like `#/Calendar/Schedule`) backed by
server endpoints that return HTML or JSON.

## Login (verified with the early spike script (since removed))

1. `GET https://auth.vklass.se/credentials` -> hidden `__RequestVerificationToken` + cookies
2. `POST https://auth.vklass.se/credentials/signin` (form: token, `Username`, `Password`,
   `RememberMe=false`) -> 302 on success, 200 on bad credentials
3. Follow the redirect chain so `custodian.vklass.se` gets its session cookies

**Gotcha (cost us a debugging round):** the sign-in response clears cookies
(`LogoutRedirectURL`, `_vk-RememberMe`, and a first `se.vklass.authentication`) with
expired, empty `Set-Cookie` headers. aiohttp's cookie jar keeps those and sends them back,
and the next hop, `auth.vklass.se/process`, answers **403**. urllib's jar drops them, which
is why the first spike worked. The client drops empty-valued cookies before every hop.
`/process` also 403s if the `Accept` header is empty (aiohttp's default `*/*` is fine).
The auth cookie is ~1.5 KB; it is `secure; samesite=none; httponly` on `.vklass.se`.
Repeated logins in quick succession may get a 200 (rejected) response; avoid hammering it.

## Children

`/Home/Welcome` no longer contains student IDs (only names, care time, lunch, news).
The IDs are numeric and live in the schedule page's server-rendered HTML:

`GET https://custodian.vklass.se/Calendar/Schedule/` contains one checkbox per child:
`<input type="checkbox" name="SelectedStudentIds" value="<id>">`.
The name is the `text="..."` attribute of the wrapping `<vkau-checkable-list-item>`
(beware `disabled-text=""` just before it).

## Events

`POST https://custodian.vklass.se/Events/FullCalendar`
form: `students=<id>[,<id>...]`, `start=<ISO local>`, `end=<ISO local>`
header: `X-Requested-With: XMLHttpRequest` (the SPA sends it; unknown if required)

Returns a JSON array. Multiple comma-separated students work in one call; each event
has `context` = child's first name. Fields of interest:

| field | notes |
|---|---|
| `title` | e.g. `Svenska (9A/SV)` |
| `text` | short code, e.g. `SV`, `IDH`, `MT` |
| `start`, `end` | `YYYY-MM-DD HH:MM` local time, no tz. `end` is null for assignments |
| `location` | e.g. `1 | ANFO` (room | teacher code) |
| `eventType`, `eventTypeLabel`, `className` | 1 / `Lektion` / `vk-cl-event-lecture`; also `Uppgift` (`-assignment`), `Ledig dag` (`-vacantday`) |
| `cancelled`, `isSubstitute` | booleans, both seen as false so far |
| `allDay`, `context` | `context` is null for school-wide events like holidays |

`id`, `lectureId`, `seriesId` were null/0 for lessons, so there is no stable per-event ID;
derive one from child + start + title for HA calendar UIDs.

The schedule UI also filters by `SelectedTypes` (`lecture`, assignments, calendar events,
vacant days, plannings); the filter may be a client-side concern, not sent in the POST.

## School breaks

The endpoint returns nothing on lesson-free days. Week 44 (autumn break) legitimately
returned no events, so an empty list is not an error.

## Open questions

- Is `X-Requested-With` required? Is a longer range (e.g. a term) accepted?
- How long does a session last, and what does an expired one return (redirect to auth?)
- What does a cancelled or substituted lesson look like (none seen yet)?

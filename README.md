# vklass-ha

Home Assistant integration that shows each child's school schedule, tests/homework and
(optionally) lunch from [Vklass](https://vklass.se).

Vklass has no public API, and its guardian site now sits behind bot protection that a
script cannot log in through. This integration therefore reads the **calendar
subscription** ("Prenumerera på schema") that Vklass publishes for calendar apps. It
needs no password, only the secret link for each child. It is unofficial and may break
when Vklass changes the feed (see `docs/api-notes.md`).

## Requirements

- Home Assistant 2025.1 or newer
- A Vklass guardian account, to copy each child's calendar link
- Optional: your school's page on [skolmaten.se](https://skolmaten.se) for lunch

## Get the calendar link

1. Log in to Vklass in a browser and open the schedule page (`Calendar/Schedule`).
2. Open the floating menu button (three dots) on that page and choose **Prenumerera på schema**.
3. The dialog lists one link per child. Use the copy button, or right-click the link and
   copy its address. It looks like `webcal://cal.vklass.se/<id>.ics?includeLectures=true`.

Paste it as it is: `webcal://` and `https://` links both work, and the setup form always
asks Vklass for lessons as well as tests and homework (`includeLectures=true`). Only
`cal.vklass.se` links are accepted.

Treat the link like a password: anyone who has it can read that child's schedule. Home
Assistant stores it in the config entry, so it is also in your backups.

## Install

### Manual

1. Copy `custom_components/vklass` from this repo into your Home Assistant config folder,
   so you end up with `<config>/custom_components/vklass/__init__.py`. (The component
   bundles the library, so that one folder is all you need.)
2. Restart Home Assistant.
3. Settings -> Devices & services -> Add integration -> **Vklass**. Enter the child's
   name and calendar link, and optionally the school's skolmaten.se link (for example
   `https://skolmaten.se/yourschool`, or the RSS link behind it). **Add the integration
   once per child.** Setup fetches the calendar (and the menu) once and tells you if the
   link is wrong.

### HACS (custom repository)

HACS -> three-dot menu -> Custom repositories -> add
`https://github.com/FredrikL/vklass-ha` with category **Integration**, install
**Vklass**, restart Home Assistant, then add the integration as in step 3 above.

## What you get

Each child becomes a device with up to three sensors:

- `sensor.<child>_next_school_day` - state is when the next school day starts (a
  timestamp, handy for alarms). Attributes: `date`, `lesson_count`, `last_end`,
  `lessons[]` (start, end, start_at, end_at, title, code, location, cancelled) and a
  printable `summary`. `schedule[]` holds the same per-day data for today (if it has
  lessons) followed by the next school day, so a card can hide lessons that have ended.
  "Next" means the next day with lessons, so Friday shows Monday and a school break shows
  the first day back. `location` is `room | teacher`.
- `sensor.<child>_upcoming_tests_and_homework` - state is the number of items in the next
  14 days. Attributes: `items[]` (title, type, due, date, days_until), `tests[]` and
  `next_test`. The type is `test`, `homework`, `submission` or `other`, guessed from the
  title (`Prov...`, `Läxa...`, `Inlämning...`).
- `sensor.<child>_lunch` (only if you added a skolmaten.se link) - state is the next
  published lunch menu from today onward, or unknown if there is none. Attributes:
  `date`, `dishes[]` and `upcoming[]` (every published day).

The calendar and the menu are fetched every 12 hours; the next school day and the
assignment countdown are recomputed at midnight, so they stay correct in between.

Each child has their own entry, so siblings at the same school each need the lunch link
if you want a lunch sensor for both. The lunch sensor is created when the entry is set
up. To add or change a lunch link later, remove the entry and add it again.

### Limits of the calendar feed

- It covers about a month ahead.
- **Cancelled lessons are not marked**, because the feed has no such flag, so `cancelled`
  stays false. (If Vklass starts sending the standard `STATUS:CANCELLED`, it is picked up.)
- Tests and homework appear as all-day entries; their due time is read from the entry's
  description when there is one.
- Lunch is not part of the feed, so it comes from Skolmaten instead (school-wide, not
  per child). If Skolmaten is unreachable the last menu is kept and the schedule is
  unaffected; days in the past drop out of the sensor by date.
- There is no per-lesson cancelled or substitute information, and no school-wide
  holidays; a school break simply has no lessons.

### If something stops working

- **Vklass no longer recognises the link** (it was regenerated, or mistyped): Home
  Assistant shows a re-authentication prompt (Settings -> Devices & services -> Vklass ->
  Reconfigure). Paste the new link from "Prenumerera på schema".
- **The sensors turn unavailable and the log says the request was refused or "possibly
  bot protection"**: Vklass is blocking the request. This is retried at the next 12 hour
  update. If it persists, open an issue; it may mean the feed has been put behind the
  same protection as the login.
- **A wrong link is rejected during setup** with "Vklass does not recognise this
  calendar link"; an empty answer from Vklass means exactly that.

### Upgrading from 0.1

Version 0.1 logged in with a username and password, which Vklass's bot protection now
blocks. Remove the old Vklass entry (it shows a migration error) and add the integration
once per child as described above. Remove the old entry first and your entity ids stay
the same. The lunch sensor now needs a skolmaten.se link.

### Dashboard examples

Replace `alva` with your child's name as it appears in the entity ids.

Upcoming lessons: today's lessons that have not ended yet, then the next school day. The
card uses `now()`, so it re-renders every minute and a lesson drops off when it ends.

```yaml
type: markdown
title: Schema
content: |
  {% set names = ['Måndag','Tisdag','Onsdag','Torsdag','Fredag','Lördag','Söndag'] %}
  {% set days = state_attr('sensor.alva_next_school_day', 'schedule') or [] %}
  {% set ns = namespace(shown=false) %}
  {% for d in days %}
  {% set r = namespace(rest=[]) %}
  {% for l in d.lessons %}
  {% if as_datetime(l.end_at or l.start_at) > now() %}{% set r.rest = r.rest + [l] %}{% endif %}
  {% endfor %}
  {% if r.rest %}{% set ns.shown = true %}
  **{{ 'Idag' if d.date == now().date().isoformat() else names[as_datetime(d.date).weekday()] ~ ' ' ~ as_datetime(d.date).day ~ '/' ~ as_datetime(d.date).month }}**

  {% for l in r.rest %}
  - {{ l.start }}–{{ l.end or '?' }} {{ l.title }}{{ ' (' ~ l.location ~ ')' if l.location }}
  {% endfor %}

  {% endif %}
  {% endfor %}
  {% if not ns.shown %}Inga kommande lektioner.{% endif %}
```

Lunch (needs the skolmaten.se link), tests and homework. Lunch uses the `dishes`
attribute, since the sensor state is cut off at 255 characters:

```yaml
type: markdown
content: >
  {% set dishes = state_attr('sensor.alva_lunch', 'dishes') or [] %}
  {% if dishes %}**Lunch {{ state_attr('sensor.alva_lunch', 'date') }}**

  {% for d in dishes %}
  - {{ d }}
  {% endfor %}{% endif %}

  {% for i in state_attr('sensor.alva_upcoming_tests_and_homework', 'items') or [] %}
  - {{ i.date }} ({{ i.type }}): {{ i.title }}
  {% endfor %}
```

## Development

```
vklass/                    async Python library (calendar feed, lunch menu)
custom_components/vklass/  the Home Assistant integration
  vklass_api/              generated copy of the library, see below
scripts/
  sync_lib.sh              copy vklass/src/vklass into the component
  live_check.py            run the library against the real services
docs/api-notes.md          what we know about the Vklass feed and why login was dropped
```

```sh
python3 -m venv .venv && .venv/bin/pip install -e './vklass[test]'
(cd vklass && ../.venv/bin/python -m pytest)

# against the real services (the link is a secret, so pass it via the environment):
VKLASS_FEED_URL='webcal://cal.vklass.se/<id>.ics' SKOLMATEN_URL='https://skolmaten.se/<school>' \
  .venv/bin/python scripts/live_check.py
```

After changing anything in `vklass/src/vklass`, run `./scripts/sync_lib.sh` and commit the
updated copy in `custom_components/vklass/vklass_api/`, since that copy is what gets
installed.

The library is tested (including a fake feed server) and parses a real feed. The
component has not yet been run inside a real Home Assistant instance after the switch to
the calendar feed.

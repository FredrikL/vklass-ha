# vklass-ha

Home Assistant integration that shows each child's school schedule, tests/homework and
lunch from [Vklass](https://vklass.se).

Vklass has no public API, so this logs in to the guardian web UI like a browser and reads
the same endpoints it uses (see `docs/api-notes.md`). It is unofficial and may break when
Vklass changes its pages.

## Requirements

- Home Assistant 2025.1 or newer
- A Vklass guardian **username and password**. BankID is not supported; if you have no
  password, use "Glömt inloggningsuppgifter?" on auth.vklass.se to set one up.

## Install

### Manual

1. Copy `custom_components/vklass` from this repo into your Home Assistant config folder,
   so you end up with `<config>/custom_components/vklass/__init__.py`. (The component
   bundles the library, so that one folder is all you need.)
2. Restart Home Assistant.
3. Settings -> Devices & services -> Add integration -> **Vklass**, and enter your
   username and password.

### HACS (custom repository)

Once this repo is on GitHub: HACS -> three-dot menu -> Custom repositories -> add the
repo URL with category **Integration**, install **Vklass**, restart Home Assistant, then
add the integration as in step 3 above.

The `OWNER` placeholders in `custom_components/vklass/manifest.json` need your GitHub
account before this works.

## What you get

Each child becomes a device with three sensors:

- `sensor.<child>_next_school_day` - state is when the next school day starts (a
  timestamp, handy for alarms). Attributes: `date`, `lesson_count`, `last_end`,
  `lessons[]` (start, end, start_at, end_at, title, code, location, cancelled) and a
  printable `summary`. `schedule[]` holds the same per-day data for today (if it has
  lessons) followed by the next school day, so a card can hide lessons that have ended.
  "Next" means the next day with lessons, so Friday shows Monday and a school break shows
  the first day back.
- `sensor.<child>_upcoming_tests_and_homework` - state is the number of items in the next
  14 days. Attributes: `items[]` (title, type, due, date, days_until), `tests[]` and
  `next_test`. The type is `test`, `homework`, `submission` or `other`, guessed from the
  title (`Prov...`, `Läxa...`, `Inlämning...`).
- `sensor.<child>_lunch` - state is the lunch on the next school day, or unknown if the
  school has not published a menu that far (Vklass lists only about today + four
  weekdays). Attributes: `date`, `dishes[]` and `upcoming[]` (every published day).

Data is fetched every 12 hours; the next school day and the assignment countdown are
recomputed at midnight, so they stay correct in between. A child added in Vklass later appears after reloading the
integration. If the password changes, Home Assistant asks you to re-enter it.

### Dashboard example

Replace `alva` with your child's name as it appears in the entity ids.

```yaml
type: markdown
content: >
  **{{ state_attr('sensor.alva_next_school_day', 'date') }}**
  {{ state_attr('sensor.alva_next_school_day', 'summary') }}

  Lunch: {{ states('sensor.alva_lunch') }}

  {% for i in state_attr('sensor.alva_upcoming_tests_and_homework', 'items') %}
  - {{ i.date }} ({{ i.type }}): {{ i.title }}
  {% endfor %}
```

## Development

```
vklass/                    async Python library (login, children, events, lunch)
custom_components/vklass/  the Home Assistant integration
  vklass_api/              generated copy of the library, see below
scripts/
  sync_lib.sh              copy vklass/src/vklass into the component
  live_check.py            run the library against the real service
docs/api-notes.md          what we know about the Vklass endpoints
```

```sh
python3 -m venv .venv && .venv/bin/pip install -e './vklass[test]'
(cd vklass && ../.venv/bin/python -m pytest)

# against your real account (credentials via environment, never on the command line):
VKLASS_USER=... VKLASS_PASS=... .venv/bin/python scripts/live_check.py
```

After changing anything in `vklass/src/vklass`, run `./scripts/sync_lib.sh` and commit the
updated copy in `custom_components/vklass/vklass_api/`, since that copy is what gets
installed.

The component has not yet been run inside a real Home Assistant instance; the library is
tested (including against a fake Vklass server) and has been run against a real account.

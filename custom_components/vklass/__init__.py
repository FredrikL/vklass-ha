"""The Vklass integration: school schedule, tests, homework and lunch per child."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import CONF_LUNCH_URL
from .coordinator import VklassConfigEntry, VklassCoordinator
from .vklass_api import Child, VklassClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: VklassConfigEntry) -> bool:
    client = VklassClient(
        async_get_clientsession(hass),
        entry.data[CONF_URL],
        lunch_url=entry.data.get(CONF_LUNCH_URL) or None,
        tz=dt_util.get_default_time_zone(),
    )
    # The entry id is the child id: it is stable and, unlike the calendar link,
    # not a secret, so it is safe in entity unique ids.
    child = Child(entry.entry_id, entry.data[CONF_NAME])
    coordinator = VklassCoordinator(hass, entry, client, child)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VklassConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version == 1:
        # Version 1 logged in with a username and password. Vklass now blocks that
        # (bot protection), so there is nothing to carry over: add one entry per
        # child with the child's calendar link instead.
        _LOGGER.error(
            "The Vklass entry %s used a username and password, which no longer "
            "works. Remove it and add the integration once per child with the "
            "child's calendar link (see the README)",
            entry.title,
        )
        return False
    return True

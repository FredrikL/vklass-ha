"""The Vklass integration: school schedule, tests and homework per child."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.util import dt as dt_util

from .coordinator import VklassCoordinator
from .vklass_api import VklassClient

PLATFORMS = [Platform.SENSOR]

VklassConfigEntry = ConfigEntry[VklassCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: VklassConfigEntry) -> bool:
    # Own session: Vklass login state lives in cookies, which must not be
    # shared with other integrations.
    client = VklassClient(
        async_create_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        tz=dt_util.get_default_time_zone(),
    )
    coordinator = VklassCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VklassConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

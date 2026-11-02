"""Config flow for Vklass: one entry per child (name + calendar link)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_NAME, CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_LUNCH_URL, DOMAIN
from .vklass_api import (
    Child,
    VklassAuthError,
    VklassClient,
    VklassConnectionError,
    VklassError,
    VklassInvalidUrl,
    feed_id,
    normalize_feed_url,
    normalize_lunch_url,
)


# Examples shown in the forms and error messages (hassfest does not allow URLs in
# strings.json itself).
EXAMPLES = {
    "feed_example": "https://cal.vklass.se/<id>.ics",
    "lunch_example": "https://skolmaten.se/<school>",
}


class VklassConfigFlow(ConfigFlow, domain=DOMAIN):
    # Version 1 used a username and password; see async_migrate_entry.
    VERSION = 2

    async def _check_feed(self, url: str) -> str | None:
        """Return an error key, or None if the calendar link works."""
        client = VklassClient(async_get_clientsession(self.hass), url)
        try:
            await client.get_events(Child("check", "check"))
        except VklassAuthError:
            return "unknown_link"
        except VklassConnectionError:
            return "cannot_connect"
        except VklassError:
            return "unknown"
        return None

    async def _check_lunch(self, feed_url: str, lunch_url: str) -> str | None:
        client = VklassClient(
            async_get_clientsession(self.hass), feed_url, lunch_url=lunch_url
        )
        try:
            if not await client.get_lunches():
                return "lunch_unavailable"
        except VklassError:
            return "lunch_unavailable"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {CONF_NAME: user_input[CONF_NAME].strip()}
            try:
                data[CONF_URL] = normalize_feed_url(user_input[CONF_URL])
            except VklassInvalidUrl:
                errors[CONF_URL] = "invalid_url"
            lunch = user_input.get(CONF_LUNCH_URL, "").strip()
            if lunch:
                try:
                    data[CONF_LUNCH_URL] = normalize_lunch_url(lunch)
                except VklassInvalidUrl:
                    errors[CONF_LUNCH_URL] = "invalid_lunch_url"
            if not data[CONF_NAME]:
                errors[CONF_NAME] = "name_required"

            if not errors:
                await self.async_set_unique_id(feed_id(data[CONF_URL]))
                self._abort_if_unique_id_configured()
                if error := await self._check_feed(data[CONF_URL]):
                    errors["base"] = error
                elif CONF_LUNCH_URL in data and (
                    error := await self._check_lunch(
                        data[CONF_URL], data[CONF_LUNCH_URL]
                    )
                ):
                    errors[CONF_LUNCH_URL] = error
                else:
                    return self.async_create_entry(title=data[CONF_NAME], data=data)

        defaults = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "")): str,
                    vol.Required(CONF_URL, default=defaults.get(CONF_URL, "")): str,
                    vol.Optional(
                        CONF_LUNCH_URL, default=defaults.get(CONF_LUNCH_URL, "")
                    ): str,
                }
            ),
            description_placeholders=EXAMPLES,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                url = normalize_feed_url(user_input[CONF_URL])
            except VklassInvalidUrl:
                errors[CONF_URL] = "invalid_url"
            else:
                if error := await self._check_feed(url):
                    errors["base"] = error
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        unique_id=feed_id(url),
                        data_updates={CONF_URL: url},
                    )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_URL): str}),
            description_placeholders={**EXAMPLES, "name": entry.data[CONF_NAME]},
            errors=errors,
        )

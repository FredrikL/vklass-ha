"""Sensors: next school day and upcoming tests/homework, per child."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import VklassConfigEntry
from .const import ASSIGNMENT_DAYS, DOMAIN
from .coordinator import ChildData, VklassCoordinator
from .vklass_api import AssignmentType


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VklassConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    # Children added to Vklass later are picked up on the next reload.
    async_add_entities(
        sensor(coordinator, entry.entry_id, child_id)
        for child_id in coordinator.data
        for sensor in (NextSchoolDaySensor, UpcomingAssignmentsSensor, LunchSensor)
    )


class _VklassChildSensor(CoordinatorEntity[VklassCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _key: str

    def __init__(
        self, coordinator: VklassCoordinator, entry_id: str, child_id: int
    ) -> None:
        super().__init__(coordinator)
        self._child_id = child_id
        child = coordinator.data[child_id].child
        self._attr_unique_id = f"{entry_id}_{child_id}_{self._key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{child_id}")},
            name=child.name,
            manufacturer="Vklass",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Between fetches the date still rolls over, so refresh the derived state.
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._midnight, hour=0, minute=0, second=5
            )
        )

    @callback
    def _midnight(self, _now: datetime) -> None:
        self.async_write_ha_state()

    @property
    def _child(self) -> ChildData | None:
        return self.coordinator.data.get(self._child_id)

    @property
    def available(self) -> bool:
        return super().available and self._child is not None


class NextSchoolDaySensor(_VklassChildSensor):
    """State is when the next school day starts, which suits alarm automations."""

    _key = "next_school_day"
    _attr_translation_key = "next_school_day"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        day = self._child.next_day
        return day.first_start if day else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        day = self._child.next_day
        attrs = day.as_dict() if day else {}
        # Today's lessons (if any) then the next school day; a card filters on end_at.
        attrs["schedule"] = [d.as_dict() for d in self._child.schedule]
        return attrs


class UpcomingAssignmentsSensor(_VklassChildSensor):
    """State is the number of tests/homework due in the next two weeks."""

    _key = "upcoming_assignments"
    _attr_translation_key = "upcoming_assignments"
    _attr_native_unit_of_measurement = "items"

    @property
    def native_value(self) -> int:
        return len(self._child.assignments)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items = [a.as_dict() for a in self._child.assignments]
        tests = [i for i in items if i["type"] == AssignmentType.TEST.value]
        return {
            "days_ahead": ASSIGNMENT_DAYS,
            "items": items,
            "tests": tests,
            "next_test": tests[0] if tests else None,
        }


class LunchSensor(_VklassChildSensor):
    """The next published lunch menu, from today onward.

    Vklass only lists a few days ahead, and menus can exist for days without
    lessons (or be missing for the next school day), so this is not tied to the
    schedule; `upcoming` lists every published day.
    """

    _key = "lunch"
    _attr_translation_key = "lunch"

    def _next_day_lunch(self):
        today = dt_util.now().date()
        return next(
            (l for l in sorted(self._child.lunches, key=lambda l: l.date) if l.date >= today),
            None,
        )

    @property
    def native_value(self) -> str | None:
        lunch = self._next_day_lunch()
        # State is capped at 255 characters.
        return ", ".join(lunch.dishes)[:255] if lunch else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        lunch = self._next_day_lunch()
        return {
            "date": lunch.date.isoformat() if lunch else None,
            "dishes": lunch.dishes if lunch else [],
            "upcoming": [
                {"date": l.date.isoformat(), "dishes": l.dishes}
                for l in self._child.lunches
            ],
        }

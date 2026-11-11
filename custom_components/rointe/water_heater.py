"""Support for Rointe water heaters."""

from __future__ import annotations

from typing import Any

from rointesdk.device import RointeDevice

from homeassistant.components.water_heater import (
    ATTR_OPERATION_MODE,
    STATE_ECO,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    LOGGER,
    ROINTE_WATER_HEATER_TYPE,
    RointeCommand,
    RointeOperationMode,
    RointePreset,
)
from .coordinator import RointeDataUpdateCoordinator
from .entity import RointeRadiatorEntity

MODE_COMFORT = "comfort"
MODE_MANUAL = RointeOperationMode.MANUAL.value
MODE_AUTO = RointeOperationMode.AUTO.value
OPERATION_MODES = [STATE_ECO, MODE_COMFORT, MODE_MANUAL, MODE_AUTO, STATE_OFF]

WATER_HEATER_TEMP_STEP = 0.5
WATER_HEATER_TEMP_MIN = 40.0
WATER_HEATER_TEMP_MAX = 75.0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up water heater entities from the config entry."""
    coordinator: RointeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    coordinator.add_entities_for_seen_keys(
        async_add_entities,
        [RointeHaWaterHeater],
        "water_heater",
        device_filter=lambda device: device.type == ROINTE_WATER_HEATER_TYPE,
    )


class RointeHaWaterHeater(RointeRadiatorEntity, WaterHeaterEntity):
    """A Rointe ACS water heater."""

    _attr_icon = "mdi:water-boiler"
    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )
    _attr_target_temperature_step = WATER_HEATER_TEMP_STEP
    _attr_operation_list = OPERATION_MODES
    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "rointe_water_heater"

    # Home Assistant renamed these temperature properties after the integration's
    # original minimum release. Support both APIs without deprecation warnings.
    if hasattr(WaterHeaterEntity, "native_temperature_unit"):
        _attr_native_temperature_unit = UnitOfTemperature.CELSIUS

        @property
        def native_current_temperature(self) -> float:
            """Return the measured water temperature."""
            return self._radiator.temp_probe

        @property
        def native_target_temperature(self) -> float:
            """Return the target water temperature."""
            return self._radiator.temp

    else:
        _attr_temperature_unit = UnitOfTemperature.CELSIUS

        @property
        def current_temperature(self) -> float:
            """Return the measured water temperature."""
            return self._radiator.temp_probe

        @property
        def target_temperature(self) -> float:
            """Return the target water temperature."""
            return self._radiator.temp

    def __init__(
        self,
        water_heater: RointeDevice,
        coordinator: RointeDataUpdateCoordinator,
    ) -> None:
        """Initialize the water heater entity."""
        super().__init__(coordinator, water_heater, unique_id=water_heater.id)

    @property
    def min_temp(self) -> float:
        """Return the minimum target temperature supported by the device."""
        if self._radiator.um_min_temp > 0:
            return self._radiator.um_min_temp

        return WATER_HEATER_TEMP_MIN

    @property
    def max_temp(self) -> float:
        """Return the maximum target temperature supported by the device."""
        if self._radiator.um_max_temp > 0:
            return self._radiator.um_max_temp

        return WATER_HEATER_TEMP_MAX

    @property
    def current_operation(self) -> str:
        """Return the current water heater operation mode."""
        if not self._radiator.power:
            return STATE_OFF

        if self._radiator.mode == RointeOperationMode.AUTO:
            return MODE_AUTO

        if self._radiator.preset == RointePreset.ECO:
            return STATE_ECO

        if self._radiator.preset == RointePreset.COMFORT:
            return MODE_COMFORT

        return MODE_MANUAL

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target water temperature."""
        target_temperature = round(kwargs[ATTR_TEMPERATURE] * 2) / 2

        if not self.min_temp <= target_temperature <= self.max_temp:
            raise HomeAssistantError(
                f"Invalid set_temperature value (must be in range "
                f"{self.min_temp}, {self.max_temp}): {target_temperature}"
            )

        LOGGER.debug("Setting water temperature to %s", target_temperature)

        if not await self.device_manager.send_command(
            self._radiator, RointeCommand.SET_TEMP, target_temperature
        ):
            raise HomeAssistantError(
                f"Failed to set temperature for {self._radiator.name}"
            )

        if operation_mode := kwargs.get(ATTR_OPERATION_MODE):
            if operation_mode != MODE_MANUAL:
                await self._async_set_operation_mode(operation_mode)

        await self.coordinator.async_refresh()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set a new water heater operation mode."""
        await self._async_set_operation_mode(operation_mode)
        await self.coordinator.async_refresh()

    async def _async_set_operation_mode(self, operation_mode: str) -> None:
        """Send an operation mode change without refreshing the coordinator."""
        LOGGER.debug("Setting water heater operation mode to %s", operation_mode)

        if operation_mode not in OPERATION_MODES:
            raise HomeAssistantError(f"Unsupported operation mode: {operation_mode}")

        if operation_mode in (STATE_ECO, MODE_COMFORT):
            command = RointeCommand.SET_PRESET
            command_arg = operation_mode
        else:
            command = RointeCommand.SET_WATER_HEATER_MODE
            command_arg = operation_mode

        if not await self.device_manager.send_command(
            self._radiator, command, command_arg
        ):
            raise HomeAssistantError(
                f"Failed to set operation mode for {self._radiator.name}"
            )

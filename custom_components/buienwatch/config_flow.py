"""Config flow for Buienwatch."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_POLL_INTERVAL,
    CONF_TRACKED_ENTITY_ID,
    DEFAULT_POLL_INTERVAL_MINUTES,
    DOMAIN,
    MAX_POLL_INTERVAL_MINUTES,
    MIN_POLL_INTERVAL_MINUTES,
)


class BuienwatchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Buienwatch."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the person/device_tracker entity to follow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            entity_id = user_input[CONF_TRACKED_ENTITY_ID]

            await self.async_set_unique_id(entity_id)
            self._abort_if_unique_id_configured()

            state = self.hass.states.get(entity_id)
            friendly_name = state.name if state else entity_id
            return self.async_create_entry(
                title=f"Rain – {friendly_name}",
                data={CONF_TRACKED_ENTITY_ID: entity_id},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TRACKED_ENTITY_ID): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["person", "device_tracker"])
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> BuienwatchOptionsFlow:
        """Create the options flow."""
        return BuienwatchOptionsFlow()


class BuienwatchOptionsFlow(OptionsFlow):
    """Handle Buienwatch options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the poll interval option."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL_MINUTES
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_POLL_INTERVAL_MINUTES,
                            max=MAX_POLL_INTERVAL_MINUTES,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="min",
                        )
                    ),
                }
            ),
        )

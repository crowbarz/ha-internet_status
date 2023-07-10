"""Config flow for Internet Status integration."""
from __future__ import annotations

from typing import Any, Tuple
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    DEFAULTS,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_TIMEOUT,
    CONF_RETRIES,
    CONF_LINKS,
    CONF_LINK_TYPE,
    CONF_PROBE_TARGET,
    CONF_PROBE_TYPE,
    CONF_REVERSE_HOSTNAME,
    CONF_CONFIGURED_IP,
    CONF_RTT_SENSOR,
    CONF_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

RTT_SCHEMA = vol.Schema(
    {
        # vol.Optional(CONF_NAME): cv.string,
        vol.Optional(
            CONF_UPDATE_INTERVAL,
            default=DEFAULTS[CONF_RTT_SENSOR][CONF_UPDATE_INTERVAL],
        ): cv.positive_int,
    }
)

LINK_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_LINK_TYPE, default=DEFAULTS[CONF_LINK_TYPE]): cv.string,
        vol.Optional(CONF_PROBE_TARGET): cv.string,
        vol.Optional(CONF_PROBE_TYPE): cv.string,
        vol.Optional(CONF_REVERSE_HOSTNAME): cv.string,
        vol.Optional(CONF_CONFIGURED_IP): cv.string,
        vol.Optional(CONF_SCAN_INTERVAL): cv.positive_time_period,
        vol.Optional(CONF_TIMEOUT): cv.socket_timeout,
        vol.Optional(CONF_RETRIES): cv.positive_int,
        vol.Optional(CONF_RTT_SENSOR): vol.Maybe(RTT_SCHEMA),
    }
)

OPTIONS_SCHEMA_ITEMS = {
    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULTS[CONF_SCAN_INTERVAL]): vol.Coerce(
        int,
        selector.NumberSelector(
            selector.NumberSelectorConfig(
                mode=selector.NumberSelectorMode.BOX, min=5, step=1
            )
        ),
    ),  # cv.positive_time_period,
    vol.Optional(CONF_TIMEOUT, default=DEFAULTS[CONF_TIMEOUT]): selector.NumberSelector(
        selector.NumberSelectorConfig(
            mode=selector.NumberSelectorMode.BOX, min=1, step=0.1
        )
    ),  # cv.socket_timeout,
    vol.Optional(CONF_RETRIES, default=DEFAULTS[CONF_RETRIES]): vol.Coerce(
        int,
        selector.NumberSelector(
            selector.NumberSelectorConfig(
                mode=selector.NumberSelectorMode.BOX, min=1, step=1
            )
        ),
    ),  # cv.positive_int,
    vol.Optional(CONF_LINKS, default=[]): selector.ObjectSelector(),
}


CONFIG_SCHEMA_ITEMS = {
    vol.Required(CONF_NAME, default=DEFAULTS[CONF_NAME]): str,
    **OPTIONS_SCHEMA_ITEMS,
}

CONFIG_SCHEMA = vol.Schema(CONFIG_SCHEMA_ITEMS)
OPTIONS_SCHEMA = vol.Schema(OPTIONS_SCHEMA_ITEMS)


def validate_input(user_input: dict[str, Any]) -> Tuple[str, dict[str, Any]]:
    """Validate the user input."""

    _LOGGER.debug("user_input: %s", user_input)
    ## Validate links schema. Throws exception if invalid.
    title = user_input.get(CONF_NAME, DEFAULTS[CONF_NAME])
    links_schema = vol.Schema([LINK_SCHEMA])
    links_schema(user_input[CONF_LINKS])

    return title, {k: v for k, v in user_input.items() if k not in [CONF_NAME]}


class InternetStatusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Internet Status."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> InternetStatusOptionsFlow:
        """Get the options flow for this handler."""
        return InternetStatusOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        step_id = "user"
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}
        if user_input is not None:
            try:
                title, config = validate_input(user_input)
            # except CannotConnect:
            #     errors["base"] = "cannot_connect"
            except Exception as exc:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
                description_placeholders["exception"] = str(exc)
            else:
                return self.async_create_entry(title=title, data={}, options=config)

        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(CONFIG_SCHEMA, user_input),
            errors=errors,
            description_placeholders=description_placeholders,
            last_step=True,
        )


class InternetStatusOptionsFlow(config_entries.OptionsFlow):
    """Handle Internet Status options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialise TFI Journey Planner options flow."""
        self.config = config_entry.options

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow for Internet Status."""
        step_id = "init"
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            try:
                _, config = validate_input(user_input)
            # except CannotConnect:
            #     errors["base"] = "cannot_connect"
            except Exception as exc:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
                description_placeholders["exception"] = str(exc)
            else:
                return self.async_create_entry(title="", data=config)

        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA,
                user_input if user_input else self.config,
            ),
            errors=errors,
            description_placeholders=description_placeholders,
        )


# class CannotConnect(HomeAssistantError):
#     """Error to indicate we cannot connect."""

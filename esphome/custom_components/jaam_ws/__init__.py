"""Client for the JAAM public service WebSocket API (/data_service_v1).

Portable across ESP32 (ESP-IDF) and Linux Host (Simulation).
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import CONF_ID, CONF_PORT
from esphome.core import CORE

from esphome import automation

CODEOWNERS = ["@reidMaks"]
DEPENDENCIES = ["network"]

CONF_HOST = "host"
CONF_PATH = "path"
CONF_REGION_INDEX = "region_index"
CONF_REGION_ID = "region_id"
CONF_SERVICE_ID = "service_id"
CONF_SERVICE_NAME = "service_name"
CONF_WEBSITE = "website"
CONF_CONTACT = "contact"
CONF_VERSION = "version"
CONF_ON_FLAGS = "on_flags"

FORBIDDEN_FIRMWARE_PATHS = {
    "/data_v1",
    "/data_v2",
    "/data_v3",
    "/data_v4",
    "/data_fusion_v1",
    "/data_touch_v1",
}


def validate_service_path(value):
    value = cv.string(value)
    if value in FORBIDDEN_FIRMWARE_PATHS:
        raise cv.Invalid(
            f"JAAM firmware endpoint '{value}' is forbidden for third-party firmware; use '/data_service_v1'."
        )
    return value


jaam_ws_ns = cg.esphome_ns.namespace("jaam_ws")
JaamWsComponent = jaam_ws_ns.class_("JaamWsComponent", cg.Component)
JaamFlagsTrigger = jaam_ws_ns.class_("JaamFlagsTrigger", automation.Trigger.template(cg.uint32))

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(JaamWsComponent),
        cv.Required(CONF_HOST): cv.string,
        cv.Optional(CONF_PORT, default=80): cv.port,
        cv.Optional(CONF_PATH, default="/data_service_v1"): validate_service_path,
        cv.Optional(CONF_SERVICE_ID, default="htram-esphome"): cv.string,
        cv.Optional(CONF_SERVICE_NAME, default="HTRAM ESPHome"): cv.string,
        cv.Optional(CONF_WEBSITE, default="https://github.com/reidMaks/htram-esphome"): cv.string,
        cv.Optional(CONF_CONTACT, default="reid.maks@gmail.com"): cv.string,
        cv.Optional(CONF_VERSION): cv.string,
        cv.Optional(CONF_REGION_ID): cv.int_,
        cv.Optional(CONF_REGION_INDEX): cv.int_,
        cv.Optional(CONF_ON_FLAGS): automation.validate_automation(
            {cv.GenerateID(CONF_ID): cv.declare_id(JaamFlagsTrigger)}
        ),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    if CORE.is_esp32:
        from esphome.components.esp32 import add_idf_component

        add_idf_component(name="espressif/esp_websocket_client", ref="1.5.0")

    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_host(config[CONF_HOST]))
    cg.add(var.set_port(config[CONF_PORT]))
    cg.add(var.set_path(config[CONF_PATH]))
    cg.add(var.set_service_id(config[CONF_SERVICE_ID]))
    cg.add(var.set_service_name(config[CONF_SERVICE_NAME]))
    cg.add(var.set_website(config[CONF_WEBSITE]))
    cg.add(var.set_contact(config[CONF_CONTACT]))
    if CONF_VERSION in config:
        cg.add(var.set_version(config[CONF_VERSION]))

    if CONF_REGION_ID in config:
        cg.add(var.set_region_id(config[CONF_REGION_ID]))
    elif CONF_REGION_INDEX in config:
        cg.add(var.set_region_index(config[CONF_REGION_INDEX]))
    else:
        cg.add(var.set_region_id(31))

    for conf in config.get(CONF_ON_FLAGS, []):
        trigger = cg.new_Pvariable(conf[CONF_ID], var)
        await automation.build_automation(trigger, [(cg.uint32, "flags")], conf)

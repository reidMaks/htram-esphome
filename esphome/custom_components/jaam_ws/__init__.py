"""Client for the JAAM alert map's WebSocket server.

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
CONF_ON_FLAGS = "on_flags"

jaam_ws_ns = cg.esphome_ns.namespace("jaam_ws")
JaamWsComponent = jaam_ws_ns.class_("JaamWsComponent", cg.Component)
JaamFlagsTrigger = jaam_ws_ns.class_("JaamFlagsTrigger", automation.Trigger.template(cg.uint32))

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(JaamWsComponent),
        cv.Required(CONF_HOST): cv.string,
        cv.Optional(CONF_PORT, default=80): cv.port,
        cv.Optional(CONF_PATH, default="/data_fusion_v1"): cv.string,
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

    if CONF_REGION_ID in config:
        cg.add(var.set_region_id(config[CONF_REGION_ID]))
    elif CONF_REGION_INDEX in config:
        cg.add(var.set_region_index(config[CONF_REGION_INDEX]))
    else:
        cg.add(var.set_region_id(31))

    for conf in config.get(CONF_ON_FLAGS, []):
        trigger = cg.new_Pvariable(conf[CONF_ID], var)
        await automation.build_automation(trigger, [(cg.uint32, "flags")], conf)

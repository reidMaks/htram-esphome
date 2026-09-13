"""Client for the JAAM alert map's WebSocket server.

Portable across ESP32 (ESP-IDF) and Linux Host (Simulation).
"""
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import automation
from esphome.const import CONF_ID, CONF_PORT
from esphome.core import CORE

CODEOWNERS = ["@reidMaks"]
DEPENDENCIES = ["network"]

CONF_HOST = "host"
CONF_ON_FLAGS = "on_flags"

jaam_ws_ns = cg.esphome_ns.namespace("jaam_ws")
JaamWsComponent = jaam_ws_ns.class_("JaamWsComponent", cg.Component)
JaamFlagsTrigger = jaam_ws_ns.class_(
    "JaamFlagsTrigger", automation.Trigger.template(cg.uint32)
)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(JaamWsComponent),
        cv.Required(CONF_HOST): cv.string,
        cv.Optional(CONF_PORT, default=81): cv.port,
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

    for conf in config.get(CONF_ON_FLAGS, []):
        trigger = cg.new_Pvariable(conf[CONF_ID], var)
        await automation.build_automation(
            trigger, [(cg.uint32, "flags")], conf
        )

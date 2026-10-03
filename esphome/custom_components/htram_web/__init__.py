"""HTRAM Standalone Web Interface and REST API Component.

Provides a dedicated, mobile-optimized standalone management web UI on port 80
without requiring Home Assistant.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import CONF_ID, CONF_TRIGGER_ID

from esphome import automation

DEPENDENCIES = ["web_server_base"]

htram_web_ns = cg.esphome_ns.namespace("htram_web")
HtramWebComponent = htram_web_ns.class_("HtramWebComponent", cg.Component)

CONF_ON_SAVE_SETTINGS = "on_save_settings"
CONF_ON_OTA_UPDATE = "on_ota_update"
CONF_VERSION = "version"

HtramSaveSettingsTrigger = htram_web_ns.class_(
    "HtramSaveSettingsTrigger",
    automation.Trigger.template(cg.int_, cg.float_, cg.float_, cg.std_string),
)

HtramOtaUpdateTrigger = htram_web_ns.class_(
    "HtramOtaUpdateTrigger",
    automation.Trigger.template(),
)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(HtramWebComponent),
        cv.Optional(CONF_VERSION, default="2.0.0"): cv.string,
        cv.Optional(CONF_ON_SAVE_SETTINGS): automation.validate_automation(
            {cv.GenerateID(CONF_TRIGGER_ID): cv.declare_id(HtramSaveSettingsTrigger)}
        ),
        cv.Optional(CONF_ON_OTA_UPDATE): automation.validate_automation(
            {cv.GenerateID(CONF_TRIGGER_ID): cv.declare_id(HtramOtaUpdateTrigger)}
        ),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_version(config[CONF_VERSION]))

    for conf in config.get(CONF_ON_SAVE_SETTINGS, []):
        trigger = cg.new_Pvariable(conf[CONF_TRIGGER_ID], var)
        await automation.build_automation(
            trigger,
            [(cg.int_, "region"), (cg.float_, "lat"), (cg.float_, "lon"), (cg.std_string, "city")],
            conf,
        )

    for conf in config.get(CONF_ON_OTA_UPDATE, []):
        trigger = cg.new_Pvariable(conf[CONF_TRIGGER_ID], var)
        await automation.build_automation(trigger, [], conf)

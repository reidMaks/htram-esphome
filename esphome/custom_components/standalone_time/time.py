import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import time as time_
from esphome.const import CONF_ID

standalone_time_ns = cg.esphome_ns.namespace("standalone_time")
StandaloneTime = standalone_time_ns.class_("StandaloneTime", time_.RealTimeClock)

CONFIG_SCHEMA = time_.TIME_SCHEMA.extend(
    {
        cv.GenerateID(): cv.declare_id(StandaloneTime),
    }
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await time_.register_time(var, config)

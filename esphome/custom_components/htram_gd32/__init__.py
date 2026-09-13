import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import uart
from esphome.const import CONF_ID

DEPENDENCIES = ['uart']
AUTO_LOAD = ['sensor', 'text_sensor', 'binary_sensor', 'switch', 'display']

htram_gd32_ns = cg.esphome_ns.namespace('htram_gd32')
HtramGd32Component = htram_gd32_ns.class_('HtramGd32Component', cg.Component, uart.UARTDevice)

CONF_SIMULATION_MODE = "simulation_mode"

CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(HtramGd32Component),
    cv.Optional(CONF_SIMULATION_MODE, default=False): cv.boolean,
}).extend(cv.COMPONENT_SCHEMA).extend(uart.UART_DEVICE_SCHEMA)

def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    yield cg.register_component(var, config)
    yield uart.register_uart_device(var, config)
    if config[CONF_SIMULATION_MODE]:
        cg.add(var.set_simulation_mode(True))

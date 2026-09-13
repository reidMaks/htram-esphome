import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import automation
from esphome.const import CONF_ID, CONF_PRIORITY, CONF_TRIGGER_ID

# Namespace
htram_arbiter_ns = cg.esphome_ns.namespace('htram_arbiter')
HtramArbiter = htram_arbiter_ns.class_('HtramArbiter', cg.Component)
ArbiterTrigger = htram_arbiter_ns.class_('ArbiterTrigger', automation.Trigger.template())

CONF_HTRAM_ARBITER_ID = 'htram_arbiter_id'
CONF_EVENTS = 'events'
CONF_EVENT = 'event'
CONF_CONTEXT = 'context'
CONF_NAME = 'name'
CONF_THEN = 'then'

EVENT_HANDLER_SCHEMA = cv.Schema({
    cv.Required(CONF_EVENT): cv.string,
    cv.Optional(CONF_CONTEXT, default="clock"): cv.string,
    cv.Optional(CONF_PRIORITY, default=50): cv.int_,
    cv.Optional(CONF_NAME, default=""): cv.string,
    cv.Required(CONF_THEN): automation.validate_automation({
        cv.GenerateID(CONF_TRIGGER_ID): cv.declare_id(ArbiterTrigger),
    }),
})

CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(HtramArbiter),
    cv.Optional(CONF_EVENTS): cv.ensure_list(EVENT_HANDLER_SCHEMA),
}).extend(cv.COMPONENT_SCHEMA)


def final_validate(config):
    events = config.get(CONF_EVENTS, [])
    seen = {}
    for item in events:
        key = (item[CONF_EVENT], item[CONF_CONTEXT])
        prio = item[CONF_PRIORITY]
        name = item.get(CONF_NAME, "unnamed")
        if key in seen:
            existing_name, existing_prio = seen[key]
            if existing_prio == prio:
                raise cv.Invalid(
                    f"\n\n======================================================================\n"
                    f"[ERROR] HTRAM Hardware Event Collision Detected!\n"
                    f"Event '{key[0]}' in Context '{key[1]}' is declared with identical priority {prio} by:\n"
                    f"  1) '{existing_name}'\n"
                    f"  2) '{name}'\n"
                    f"Conflict resolution required: adjust priorities or remap gestures in YAML packages.\n"
                    f"======================================================================\n"
                )
        seen[key] = (name, prio)
    return config


FINAL_VALIDATE_SCHEMA = final_validate


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    events = config.get(CONF_EVENTS, [])
    # Sort events by priority descending:
    sorted_events = sorted(events, key=lambda x: x[CONF_PRIORITY], reverse=True)

    for h in sorted_events:
        for trig_conf in h[CONF_THEN]:
            trigger = cg.new_Pvariable(trig_conf[CONF_TRIGGER_ID])
            await automation.build_automation(trigger, [], trig_conf)
            cg.add(var.add_handler(
                h[CONF_EVENT],
                h[CONF_CONTEXT],
                h[CONF_PRIORITY],
                h.get(CONF_NAME, ""),
                trigger,
            ))

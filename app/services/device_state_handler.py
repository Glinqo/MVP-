"""Device state evidence handler - Phase 7.

Accepts manual recording of device states (sensor LED, PLC input LED, online monitor)
and maps them to ability nodes for graph updates.
"""

from .learning_event_store import append_normalized_event
from .graph_update_engine import record_student_graph_event


# Mapping from device state fields to ability IDs
STATE_ABILITY_MAP = {
    "sensor_led": ["sensor_led_observation", "sensor_wiring_judgement"],
    "plc_input_led": ["input_led_compare", "plc_input_monitoring", "plc_input_common_terminal"],
    "online_monitor": ["plc_input_monitoring", "plc_io_address_mapping"],
    "cylinder_action": ["input_no_response_fault_scope", "plc_input_monitoring"],
    "power_status": ["dc24v_power_check", "electrical_safety_check"],
    "safety_confirmed": ["electrical_safety_check", "power_isolation_confirmation"],
}


def record_device_state(payload):
    """Record a device state observation and map to ability evidence.

    Input:
    {
        "session_id": "xxx",
        "scenario_id": "SCN_SENSOR_LED_ON_PLC_LED_OFF",
        "sensor_led": "on",
        "plc_input_led": "off",
        "online_monitor": "off",
        "note": "??????? PLC ?????"
    }

    Returns:
        dict with mapped abilities and event confirmation
    """
    session_id = payload.get("session_id", "default")
    scenario_id = payload.get("scenario_id", "")
    note = payload.get("note", "")

    # Determine which abilities are affected
    mapped_abilities = set()
    state_fields = ["sensor_led", "plc_input_led", "online_monitor",
                    "cylinder_action", "power_status", "safety_confirmed"]

    for field in state_fields:
        if field in payload and payload[field] is not None:
            abilities = STATE_ABILITY_MAP.get(field, [])
            mapped_abilities.update(abilities)

    ability_ids = list(mapped_abilities)

    # Build event
    event = {
        "session_id": session_id,
        "event_type": "device_state_recorded",
        "scenario_id": scenario_id,
        "ability_ids": ability_ids,
        "note": note or _build_device_note(payload),
        "outcome": "recorded",
        "polarity": "neutral",
    }

    # Record normalized event (Phase 1)
    norm_result = append_normalized_event(session_id, event)

    # Also record to student graph
    graph_result = record_student_graph_event({
        "session_id": session_id,
        "event_type": "device_state_recorded",
        "ability_ids": ability_ids,
        "note": note or _build_device_note(payload),
        "source": "device_state_manual",
    })

    return {
        "saved": True,
        "session_id": session_id,
        "mapped_abilities": ability_ids,
        "state_recorded": {k: v for k, v in payload.items() if k in state_fields},
        "diagnostic_hint": _generate_diagnostic_hint(payload),
    }


def _build_device_note(payload):
    """Build a human-readable note from device state fields."""
    parts = []
    if "sensor_led" in payload:
        parts.append(f"????:{payload['sensor_led']}")
    if "plc_input_led" in payload:
        parts.append(f"PLC???:{payload['plc_input_led']}")
    if "online_monitor" in payload:
        parts.append(f"????:{payload['online_monitor']}")
    if "cylinder_action" in payload:
        parts.append(f"??:{payload['cylinder_action']}")
    return "?".join(parts) if parts else "??????"


def _generate_diagnostic_hint(payload):
    """Generate a diagnostic hint based on the observed state pattern."""
    sensor_led = payload.get("sensor_led", "")
    plc_led = payload.get("plc_input_led", "")
    monitor = payload.get("online_monitor", "")

    if sensor_led == "on" and plc_led == "off":
        return {
            "direction": "??????",
            "hint": "????????PLC???????????????????????????",
            "next_abilities": ["plc_input_common_terminal", "sensor_wiring_judgement"],
        }
    if sensor_led == "on" and plc_led == "on" and monitor == "off":
        return {
            "direction": "??????",
            "hint": "???????PLC???????????I/O????????????",
            "next_abilities": ["plc_io_address_mapping", "program_variable_lookup"],
        }
    if sensor_led == "off":
        return {
            "direction": "??????",
            "hint": "???????????24V???????????????????",
            "next_abilities": ["sensor_led_observation", "dc24v_power_check", "sensor_type_identification"],
        }
    if sensor_led == "on" and plc_led == "on" and monitor != "off":
        return {
            "direction": "??????",
            "hint": "????PLC??????????????????????????",
            "next_abilities": ["program_variable_lookup", "input_no_response_fault_scope"],
        }

    return {
        "direction": "??????",
        "hint": "??????????????????????",
        "next_abilities": ["sensor_led_observation", "input_led_compare", "plc_input_monitoring"],
    }

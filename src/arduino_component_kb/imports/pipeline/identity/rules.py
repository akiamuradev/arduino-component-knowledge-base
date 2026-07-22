"""Versioned declarative scoring rules for component category candidates."""

from __future__ import annotations

from dataclasses import dataclass

from arduino_component_kb.imports.pipeline.models import NormalizationProfile

IDENTITY_RULE_VERSION = "1.0.0"
AUTO_RESOLVE_SCORE = 65
AUTO_RESOLVE_MARGIN = 15
REVIEW_SCORE = 35


@dataclass(frozen=True, slots=True)
class CategoryRule:
    category_key: str
    tokens: frozenset[str]
    taxonomy_prefixes: tuple[str, ...] = ()
    profile: NormalizationProfile | None = None
    taxonomy_weight: int = 20


def _rule(
    key: str,
    tokens: tuple[str, ...],
    prefixes: tuple[str, ...] = (),
    profile: NormalizationProfile | None = None,
    taxonomy_weight: int = 20,
) -> CategoryRule:
    return CategoryRule(key, frozenset(tokens), prefixes, profile, taxonomy_weight)


CATEGORY_RULES: tuple[CategoryRule, ...] = (
    _rule(
        "sensors",
        (
            "sensor",
            "sensing",
            "temperature",
            "humidity",
            "pressure",
            "ultrasonic",
            "ranger",
            "distance",
            "proximity",
            "accelerometer",
            "gyroscope",
            "light sensor",
            "gas sensor",
        ),
        ("sensor.",),
        NormalizationProfile.SENSOR,
    ),
    _rule(
        "displays",
        ("display", "oled", "lcd", "screen", "e ink", "epaper"),
        ("display.",),
        NormalizationProfile.DISPLAY,
    ),
    _rule(
        "actuators",
        ("actuator", "motor", "relay", "servo", "solenoid", "pump", "buzzer"),
        ("actuator.",),
        NormalizationProfile.ACTUATOR,
    ),
    _rule(
        "input",
        ("button", "switch", "joystick", "keypad", "encoder", "potentiometer"),
    ),
    _rule(
        "power",
        ("battery", "charger", "power supply", "dc dc", "converter", "power module"),
    ),
    _rule(
        "communication",
        ("wifi", "wi fi", "bluetooth", "lora", "can bus", "radio", "wireless", "ethernet"),
        ("communication.frequency.", "communication.link_budget"),
        NormalizationProfile.COMMUNICATION,
    ),
    _rule(
        "boards",
        ("development board", "board", "shield", "xiao", "seeeduino", "wio terminal"),
        ("board.",),
        NormalizationProfile.BOARD,
    ),
    _rule(
        "connectors",
        ("connector", "terminal", "adapter", "socket", "header"),
        ("mechanical.connector",),
        taxonomy_weight=10,
    ),
    _rule(
        "semiconductors",
        ("transistor", "diode", "mosfet", "thyristor", "triac", "led"),
    ),
)

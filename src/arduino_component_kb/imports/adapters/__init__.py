"""Versioned source-specific component adapters."""

from arduino_component_kb.imports.adapters.alexgyver import AlexGyverAdapter
from arduino_component_kb.imports.adapters.arduino_tex import ArduinoTexAdapter
from arduino_component_kb.imports.adapters.base import ComponentSourceAdapter
from arduino_component_kb.imports.adapters.portal_pk import PortalPkAdapter

DEFAULT_ADAPTERS: tuple[ComponentSourceAdapter, ...] = (
    ArduinoTexAdapter(),
    PortalPkAdapter(),
    AlexGyverAdapter(),
)

__all__ = [
    "DEFAULT_ADAPTERS",
    "AlexGyverAdapter",
    "ArduinoTexAdapter",
    "ComponentSourceAdapter",
    "PortalPkAdapter",
]

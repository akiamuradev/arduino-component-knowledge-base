"""Versioned source-specific component adapters."""

from arduino_component_kb.imports.adapters.alexgyver import AlexGyverAdapter
from arduino_component_kb.imports.adapters.arduino_tex import ArduinoTexAdapter
from arduino_component_kb.imports.adapters.base import ComponentSourceAdapter
from arduino_component_kb.imports.adapters.kicad_symbols import KicadSymbolsAdapter
from arduino_component_kb.imports.adapters.portal_pk import PortalPkAdapter
from arduino_component_kb.imports.adapters.repository import RepositorySourceAdapter
from arduino_component_kb.imports.adapters.seeed_wiki import SeeedWikiAdapter

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
    "KicadSymbolsAdapter",
    "PortalPkAdapter",
    "RepositorySourceAdapter",
    "SeeedWikiAdapter",
]

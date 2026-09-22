"""Controlled, case-sensitive unit vocabulary; bytes use binary, bits SI prefixes."""

from decimal import Decimal, localcontext

# symbol -> (preferred display symbol, family, scale to base unit).
_UNITS: dict[str, tuple[str, str, Decimal]] = {}


def _register(family: str, preferred: str, scale: str, *aliases: str) -> None:
    for symbol in (preferred, *aliases):
        _UNITS[symbol] = (preferred, family, Decimal(scale))


for preferred, scale, aliases in (
    ("Б", "1", ("B", "byte", "bytes", "байт", "байта", "байтов")),
    ("КБ", "1024", ("KB", "KiB", "КиБ", "кБ", "килобайт")),
    ("МБ", "1048576", ("MB", "MiB", "МиБ", "мегабайт")),
    ("ГБ", "1073741824", ("GB", "GiB", "ГиБ", "гигабайт")),
):
    _register("data_size_bytes", preferred, scale, *aliases)

for family, entries in (
    (
        "data_size_bits",
        (
            ("бит", "1", "bit"),
            ("кбит", "1000", "kbit"),
            ("Мбит", "1000000", "Mbit"),
            ("Гбит", "1000000000", "Gbit"),
        ),
    ),
    (
        "frequency",
        (
            ("Гц", "1", "Hz"),
            ("кГц", "1000", "kHz"),
            ("МГц", "1000000", "MHz"),
            ("ГГц", "1000000000", "GHz"),
        ),
    ),
    ("voltage", (("мВ", "0.001", "mV"), ("В", "1", "V"), ("кВ", "1000", "kV"))),
    ("current", (("мкА", "0.000001", "uA", "µA", "μA"), ("мА", "0.001", "mA"), ("А", "1", "A"))),
    (
        "resistance",
        (
            ("Ом", "1", "ohm", "Ω", "Ω"),
            ("кОм", "1000", "kΩ", "kohm"),
            ("МОм", "1000000", "MΩ", "Mohm"),
        ),
    ),
    (
        "capacitance",
        (
            ("пФ", "0.000000000001", "pF"),
            ("нФ", "0.000000001", "nF"),
            ("мкФ", "0.000001", "uF", "µF", "μF"),
            ("мФ", "0.001", "mF"),
            ("Ф", "1", "F"),
        ),
    ),
    ("time", (("мкс", "0.000001", "us", "µs", "μs"), ("мс", "0.001", "ms"), ("с", "1", "s"))),
    ("length", (("мм", "0.001", "mm"), ("см", "0.01", "cm"), ("м", "1", "m"))),
):
    for entry in entries:
        _register(family, entry[0], entry[1], *entry[2:])


def normalize_unit_symbol(symbol: str) -> str:
    stripped = symbol.strip()
    entry = _UNITS.get(stripped)
    return entry[0] if entry else stripped


def unit_family(symbol: str | None) -> str | None:
    entry = _UNITS.get((symbol or "").strip())
    return entry[1] if entry else None


def convert_numeric_value(
    value: Decimal, from_unit: str | None, to_unit: str | None
) -> Decimal | None:
    if not value.is_finite():
        return None
    if value.is_zero():
        value = Decimal(0)
    source, target = normalize_unit_symbol(from_unit or ""), normalize_unit_symbol(to_unit or "")
    if source == target:
        return value
    left, right = _UNITS.get(source), _UNITS.get(target)
    if left is None or right is None or left[1] != right[1]:
        return None
    with localcontext() as context:
        context.prec = 64
        return value * left[2] / right[2]


def fits_numeric_storage(value: Decimal) -> bool:
    """Reject overflow/precision loss rather than letting NUMERIC(24,8) round it."""
    if not value.is_finite():
        return False
    if value.is_zero():
        return True
    if value.adjusted() > 15:
        return False
    # Inspect digits instead of normalize(): a hostile exponent must not overflow
    # the decimal context or underflow into a silently accepted zero.
    _, digits, exponent = value.as_tuple()
    trailing_zeros = 0
    for digit in reversed(digits):
        if digit != 0:
            break
        trailing_zeros += 1
    return isinstance(exponent, int) and exponent + trailing_zeros >= -8

"""Human-readable reference identifiers for records that use integer primary keys."""

PREFIXES = {
    "finding": ("FND", 4),
    "assessment": ("ASM", 6),
    "evidence": ("EVD", 5),
    "run": ("RUN", 4),
    "remediation": ("REM", 4),
    "report": ("RPT", 4),
}


def make_ref(kind: str, pk: int | None) -> str | None:
    if pk is None:
        return None
    prefix, width = PREFIXES[kind]
    return f"{prefix}-{pk:0{width}d}"


def parse_ref(kind: str, value: str | int) -> int | None:
    """Accept either a raw integer id or a reference such as FND-0012."""
    if isinstance(value, int):
        return value
    text = str(value).strip().upper()
    if text.isdigit():
        return int(text)
    prefix, _ = PREFIXES[kind]
    if text.startswith(prefix + "-"):
        tail = text[len(prefix) + 1 :]
        if tail.isdigit():
            return int(tail)
    return None

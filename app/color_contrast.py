"""A dependency-free WCAG 2.x contrast-ratio helper.

No browser, no image rendering — just the sRGB → relative-luminance → contrast
math from the WCAG 2.x spec, applied to hex colors. This is the deterministic
gate for the one artifact whose palette is otherwise "trust the eyeball":
:func:`app.share.render_share_svg`. See ``tests/test_share.py`` for the
merge-blocking assertions built on top of this module.
"""

from __future__ import annotations

__all__ = [
    "contrast_ratio",
    "meets_aa",
    "relative_luminance",
    "srgb_to_linear",
]


def _parse_hex(hex_color: str) -> tuple[int, int, int]:
    """Parse ``#rgb`` or ``#rrggbb`` (case-insensitive) into 0-255 RGB ints."""
    s = hex_color.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        raise ValueError(f"not a #rgb or #rrggbb color: {hex_color!r}")
    try:
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError as exc:
        raise ValueError(f"not a valid hex color: {hex_color!r}") from exc
    return r, g, b


def srgb_to_linear(channel: float) -> float:
    """Convert one 0-255 sRGB channel value to linear-light, per WCAG 2.x."""
    c = channel / 255.0
    if c <= 0.04045:
        return c / 12.92
    return float(((c + 0.055) / 1.055) ** 2.4)


def relative_luminance(hex_color: str) -> float:
    """WCAG 2.x relative luminance (0=black .. 1=white) of a ``#rgb``/``#rrggbb`` color."""
    r, g, b = _parse_hex(hex_color)
    r_lin, g_lin, b_lin = srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b)
    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """WCAG 2.x contrast ratio between two colors, in [1, 21]."""
    l1 = relative_luminance(fg_hex)
    l2 = relative_luminance(bg_hex)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def meets_aa(fg: str, bg: str, large: bool = False) -> bool:
    """Whether ``fg`` on ``bg`` meets WCAG 2.x AA (>=4.5 normal, >=3.0 large text)."""
    threshold = 3.0 if large else 4.5
    return contrast_ratio(fg, bg) >= threshold

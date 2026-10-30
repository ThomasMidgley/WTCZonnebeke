"""Hulpfuncties voor de huisstijlkleuren (contrast volgens WCAG 2.1)."""

import re

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(c))):02X}" for c in rgb)


def luminance(value):
    def channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in hex_to_rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def darken_until(value, background="#FFFFFF", target=4.5):
    """Maak een kleur donkerder tot ze leesbaar is als tekst op de achtergrond."""
    rgb = hex_to_rgb(value)
    for step in range(0, 101):
        factor = 1 - step / 100
        candidate = rgb_to_hex(tuple(c * factor for c in rgb))
        if contrast(candidate, background) >= target:
            return candidate
    return "#000000"


def readable_on(value):
    """Wit of antraciet als tekstkleur op een gekleurd vlak."""
    return "#FFFFFF" if contrast(value, "#FFFFFF") >= contrast(value, "#1A1A1A") else "#1A1A1A"

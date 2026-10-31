import re

from django import template

register = template.Library()

NATIONAL_NUMBER = re.compile(r"^(\d{2}\.\d{2}\.\d{2})-\d{3}\.\d{2}$")


@register.filter
def mask_national_number(value):
    """Een rijksregisternummer komt nooit voluit in een mail: enkel de geboortedatum blijft zichtbaar."""
    match = NATIONAL_NUMBER.match(str(value or "").strip())
    if match:
        return f"{match.group(1)}-•••.•• (volledig nummer in de beheeromgeving)"
    return value

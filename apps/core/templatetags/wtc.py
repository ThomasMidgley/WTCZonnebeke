import re
from io import BytesIO

import qrcode
import qrcode.image.svg
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

YOUTUBE_RE = re.compile(r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})")


@register.filter
def youtube_id(url):
    match = YOUTUBE_RE.search(url or "")
    return match.group(1) if match else ""


@register.simple_tag
def qr_svg(data, label="QR-code"):
    """Inline SVG-QR-code, zonder externe dienst."""
    image = qrcode.make(data or "", image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buffer = BytesIO()
    image.save(buffer)
    svg = buffer.getvalue().decode()
    svg = svg[svg.index("<svg") :]
    svg = svg.replace("<svg ", f'<svg role="img" aria-label="{escape(label)}" class="qr" ', 1)
    return mark_safe(svg)


@register.simple_tag(takes_context=True)
def main_menu(context):
    """De pagina's onder de home die 'Tonen in menu' aangevinkt hebben."""
    from wagtail.models import Site

    request = context.get("request")
    site = Site.find_for_request(request) if request else None
    if not site:
        return []
    return site.root_page.get_children().live().public().in_menu().specific()


@register.filter
def is_current(menu_page, page):
    if not page:
        return False
    return page.pk == menu_page.pk or page.path.startswith(menu_page.path)

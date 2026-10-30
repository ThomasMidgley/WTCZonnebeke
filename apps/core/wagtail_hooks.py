from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from .models import Sponsor


class SponsorViewSet(SnippetViewSet):
    model = Sponsor
    icon = "pick"
    menu_label = "Sponsors"
    menu_name = "sponsors"
    menu_order = 200
    add_to_admin_menu = True
    list_display = ["name", "is_main", "is_visible", "sort_order"]
    list_filter = ["is_main", "is_visible"]


register_snippet(SponsorViewSet)

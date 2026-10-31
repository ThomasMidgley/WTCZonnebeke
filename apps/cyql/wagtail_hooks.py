from django.urls import path, reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.viewsets.base import ViewSetGroup
from wagtail.admin.viewsets.model import ModelViewSet
from wagtail.permission_policies import ModelPermissionPolicy

from . import views
from .models import Challenge, Member, SyncRun


class ReadOnlyPolicy(ModelPermissionPolicy):
    """Deze gegevens komen uit Cyql of uit de sync zelf; beheerders kijken enkel (en mogen opruimen)."""

    def user_has_permission(self, user, action):
        if action in ("add", "change"):
            return False
        return super().user_has_permission(user, action)

    def user_has_any_permission(self, user, actions):
        return any(self.user_has_permission(user, action) for action in actions)


class NoAddPolicy(ModelPermissionPolicy):
    """Klassementen ontstaan in Cyql; hier kies je enkel of en in welke volgorde ze getoond worden."""

    def user_has_permission(self, user, action):
        if action == "add":
            return False
        return super().user_has_permission(user, action)

    def user_has_any_permission(self, user, actions):
        return any(self.user_has_permission(user, action) for action in actions)


class ChallengeViewSet(ModelViewSet):
    model = Challenge
    icon = "list-ol"
    menu_label = "Klassementen"
    list_display = ["title", "show_on_site", "is_active", "participant_count", "scores_updated_at"]
    list_filter = ["show_on_site", "is_active"]
    form_fields = ["show_on_site", "sort_order"]
    copy_view_enabled = False

    @property
    def permission_policy(self):
        return NoAddPolicy(self.model)


class MemberViewSet(ModelViewSet):
    model = Member
    icon = "group"
    menu_label = "Leden"
    list_display = ["last_name", "first_name", "email", "status"]
    search_fields = ["first_name", "last_name", "email"]
    form_fields = []
    copy_view_enabled = False

    @property
    def permission_policy(self):
        return ReadOnlyPolicy(self.model)


class SyncRunViewSet(ModelViewSet):
    model = SyncRun
    icon = "resubmit"
    menu_label = "Synchronisaties"
    list_display = ["started_at", "ok", "message", "remaining_budget"]
    list_filter = ["ok"]
    inspect_view_enabled = True
    copy_view_enabled = False
    form_fields = []

    @property
    def permission_policy(self):
        return ReadOnlyPolicy(self.model)


class CyqlGroup(ViewSetGroup):
    menu_label = "Cyql"
    menu_icon = "resubmit"
    menu_order = 300
    items = (
        ChallengeViewSet("cyql_challenges"),
        MemberViewSet("cyql_members"),
        SyncRunViewSet("cyql_sync"),
    )


@hooks.register("register_admin_viewset")
def register_cyql_viewsets():
    return CyqlGroup()


@hooks.register("register_admin_urls")
def register_sync_now_url():
    return [path("cyql/nu-synchroniseren/", views.sync_now, name="cyql_sync_now")]


class SuperuserMenuItem(MenuItem):
    def is_shown(self, request):
        return request.user.is_superuser


@hooks.register("register_settings_menu_item")
def register_sync_now_menu_item():
    return SuperuserMenuItem("Cyql nu synchroniseren", reverse("cyql_sync_now"), icon_name="resubmit", order=900)

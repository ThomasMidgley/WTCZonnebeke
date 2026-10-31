from wagtail import hooks
from wagtail.admin.viewsets.model import ModelViewSet
from wagtail.permission_policies import ModelPermissionPolicy

from .models import SyncRun


class ReadOnlyPolicy(ModelPermissionPolicy):
    """Het verslag wordt enkel door de sync zelf geschreven; beheerders kijken en mogen opruimen."""

    def user_has_permission(self, user, action):
        if action in ("add", "change"):
            return False
        return super().user_has_permission(user, action)

    def user_has_any_permission(self, user, actions):
        return any(self.user_has_permission(user, action) for action in actions)


class SyncRunViewSet(ModelViewSet):
    model = SyncRun
    icon = "resubmit"
    menu_label = "Cyql-sync"
    menu_name = "cyql-sync"
    menu_order = 900
    add_to_settings_menu = True
    list_display = ["started_at", "ok", "message", "remaining_budget"]
    list_filter = ["ok"]
    inspect_view_enabled = True
    copy_view_enabled = False
    form_fields = []

    @property
    def permission_policy(self):
        return ReadOnlyPolicy(self.model)


@hooks.register("register_admin_viewset")
def register_sync_viewset():
    return SyncRunViewSet("cyql_sync")

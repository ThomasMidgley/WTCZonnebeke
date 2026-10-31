from django.core.exceptions import PermissionDenied
from django.urls import path, reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.viewsets.model import ModelViewSet
from wagtail.permission_policies import ModelPermissionPolicy

from . import views
from .models import Form


class SuperuserPolicy(ModelPermissionPolicy):
    def user_has_permission(self, user, action):
        return user.is_active and user.is_superuser

    def user_has_any_permission(self, user, actions):
        return self.user_has_permission(user, None)


class FormViewSet(ModelViewSet):
    model = Form
    icon = "form"
    menu_label = "Formulieren"
    add_to_admin_menu = False
    list_display = ["title", "is_active", "closes_at", "answers_link"]
    list_filter = ["is_active"]
    search_fields = ["title"]

    @property
    def permission_policy(self):
        return SuperuserPolicy(self.model)


form_viewset = FormViewSet("formulieren")


@hooks.register("register_admin_viewset")
def register_form_viewset():
    return form_viewset


def superuser_only(view):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


@hooks.register("register_admin_urls")
def register_answer_urls():
    return [
        path("formulieren/<int:pk>/antwoorden/", superuser_only(views.answers_view), name="formulier_antwoorden"),
        path("formulieren/<int:pk>/export/", superuser_only(views.answers_export), name="formulier_export"),
    ]


class SuperuserMenuItem(MenuItem):
    def is_shown(self, request):
        return request.user.is_superuser


@hooks.register("register_admin_menu_item")
def register_forms_menu():
    return SuperuserMenuItem("Formulieren", reverse("formulieren:index"), icon_name="form", name="formulieren", order=8600)

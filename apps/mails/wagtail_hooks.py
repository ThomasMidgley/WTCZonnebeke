from django.urls import path, reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem

from . import views


@hooks.register("register_admin_urls")
def register_mail_urls():
    return [
        path("e-mails/", views.index, name="mails_index"),
        path("e-mails/verstuurd/", views.log, name="mails_log"),
        path("e-mails/verstuurd/<int:pk>/opnieuw/", views.resend, name="mails_resend"),
        path("e-mails/<slug:key>/", views.edit, name="mails_edit"),
    ]


class SuperuserMenuItem(MenuItem):
    def is_shown(self, request):
        return request.user.is_superuser


@hooks.register("register_admin_menu_item")
def register_mails_menu():
    return SuperuserMenuItem("E-mails", reverse("mails_index"), icon_name="mail", name="e-mails", order=8650)

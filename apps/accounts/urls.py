from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("wachtwoord/", views.password_login_view, name="password_login"),
]

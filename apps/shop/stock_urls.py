from django.urls import path

from . import stock_views as views

app_name = "stock"
urlpatterns = [
    path("", views.to_deliver, name="to_deliver"),
    path("bestelling/<int:pk>/", views.order_detail, name="order"),
    path("bestelling/<int:pk>/<slug:action>/", views.order_action, name="order_action"),
    path("voorraad/", views.stock_overview, name="stock"),
    path("voorraad/<int:pk>/", views.adjust, name="adjust"),
    path("zoeken/", views.search, name="search"),
    path("logboek/", views.log, name="log"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
]

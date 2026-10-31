from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.timezone import localtime
from wagtail import hooks
from wagtail.admin.menu import Menu, MenuItem, SubmenuMenuItem
from wagtail.admin.viewsets.model import ModelViewSet
from wagtail.permission_policies import ModelPermissionPolicy

from apps.formulieren.services import xlsx_response_bytes
from apps.formulieren.views import xlsx_response

from .models import Order, OrderLine, Product, StockMovement
from .stock_views import can_manage_stock as is_stock_user


class ProductPolicy(ModelPermissionPolicy):
    """Artikels en prijzen beheert enkel een beheerder."""

    def user_has_permission(self, user, action):
        return user.is_active and user.is_superuser

    def user_has_any_permission(self, user, actions):
        return self.user_has_permission(user, None)


class ViewOnlyPolicy(ModelPermissionPolicy):
    """Bestellingen en het logboek wijzig je in de stock-app, niet hier. Hier kijk je enkel."""

    def user_has_permission(self, user, action):
        return action == "view" and is_stock_user(user)

    def user_has_any_permission(self, user, actions):
        return any(self.user_has_permission(user, action) for action in actions)


class ProductViewSet(ModelViewSet):
    model = Product
    icon = "tag"
    menu_label = "Artikels"
    list_display = ["title", "kind", "price", "members_only", "is_visible", "participants_link"]
    list_filter = ["kind", "members_only", "is_visible"]
    search_fields = ["title"]

    @property
    def permission_policy(self):
        return ProductPolicy(self.model)


class OrderViewSet(ModelViewSet):
    model = Order
    icon = "list-ul"
    menu_label = "Bestellingen"
    list_display = ["number", "name", "status", "total", "created_at"]
    list_filter = ["status"]
    search_fields = ["number", "name", "email"]
    inspect_view_enabled = True
    inspect_view_fields = [
        "number", "status", "name", "email", "phone", "note", "total",
        "created_at", "paid_at", "ready_at", "delivered_at", "handled_by",
    ]
    copy_view_enabled = False
    form_fields = []

    @property
    def permission_policy(self):
        return ViewOnlyPolicy(self.model)


class StockMovementViewSet(ModelViewSet):
    model = StockMovement
    icon = "history"
    menu_label = "Logboek stock"
    list_display = ["created_at", "variant", "delta", "stock_after", "reason", "user"]
    copy_view_enabled = False
    form_fields = []

    @property
    def permission_policy(self):
        return ViewOnlyPolicy(self.model)


VIEWSETS = (
    ProductViewSet("shop_products"),
    OrderViewSet("shop_orders"),
    StockMovementViewSet("shop_movements"),
)


@hooks.register("register_admin_viewset")
def register_shop_viewsets():
    return list(VIEWSETS)


class SuperuserMenuItem(MenuItem):
    def is_shown(self, request):
        return request.user.is_superuser


class StockMenuItem(MenuItem):
    def is_shown(self, request):
        return is_stock_user(request.user)


class StockSubmenu(SubmenuMenuItem):
    def is_shown(self, request):
        return is_stock_user(request.user)


@hooks.register("register_shop_menu_item")
def products_menu_item():
    return SuperuserMenuItem("Artikels", reverse("shop_products:index"), icon_name="tag", order=10)


@hooks.register("register_shop_menu_item")
def orders_menu_item():
    return StockMenuItem("Bestellingen", reverse("shop_orders:index"), icon_name="list-ul", order=20)


@hooks.register("register_shop_menu_item")
def movements_menu_item():
    return StockMenuItem("Logboek stock", reverse("shop_movements:index"), icon_name="history", order=30)


@hooks.register("register_shop_menu_item")
def stock_app_menu_item():
    return StockMenuItem("Stock-app (gsm)", reverse("stock:to_deliver"), icon_name="mobile-alt", order=40)


@hooks.register("register_admin_menu_item")
def register_shop_menu():
    menu = Menu(register_hook_name="register_shop_menu_item")
    return StockSubmenu("Webshop", menu, icon_name="tag", name="webshop", order=8500)


# ---------------------------------------------------------------- deelnemers per event


def participants_table(product):
    lines = (
        OrderLine.objects.filter(product=product, order__status__in=[*Order.OPEN, Order.DELIVERED])
        .select_related("order")
        .order_by("order__paid_at")
    )
    labels = []
    for line in lines:
        for label, _ in line.answers:
            if label not in labels:
                labels.append(label)
    header = ["Bestelling", "Betaald op", "Naam", "E-mailadres", "Gsm", "Aantal", "Bedrag"] + labels
    rows = []
    for line in lines:
        answers = dict((label, value) for label, value in line.answers)
        order = line.order
        rows.append(
            [order.number, localtime(order.paid_at).strftime("%d/%m/%Y %H:%M") if order.paid_at else "", order.name,
             order.email, order.phone, line.quantity, float(line.line_total)]
            + [answers.get(label, "") for label in labels]
        )
    return header, rows


def participants_view(request, pk):
    if not request.user.is_superuser:
        raise PermissionDenied
    product = get_object_or_404(Product, pk=pk)
    header, rows = participants_table(product)
    if request.GET.get("export"):
        return xlsx_response(xlsx_response_bytes(product.title, header, rows), f"deelnemers-{product.title}")
    total = sum(row[5] for row in rows)
    return render(request, "shop/admin_participants.html", {"product": product, "header": header, "rows": rows, "total": total})


@hooks.register("register_admin_urls")
def register_participants_url():
    return [path("webshop/deelnemers/<int:pk>/", participants_view, name="shop_participants")]

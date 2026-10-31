"""Mobiele stockomgeving voor de kledijverantwoordelijke (/stock/), als app op het startscherm (PWA)."""

from functools import wraps

from django import forms
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.views.decorators.http import require_POST

from apps.accounts.roles import STOCK_GROUP

from . import services
from .models import Order, Product, StockMovement, Variant


def can_manage_stock(user):
    return user.is_active and (user.is_superuser or user.groups.filter(name=STOCK_GROUP).exists())


def stock_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not can_manage_stock(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


@stock_required
def to_deliver(request):
    orders = Order.objects.filter(status__in=Order.OPEN).prefetch_related("lines").order_by("paid_at")
    return render(request, "stock/to_deliver.html", {"orders": orders, "tab": "leveren"})


@stock_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("lines"), pk=pk)
    return render(request, "stock/order.html", {"order": order, "tab": "leveren"})


@stock_required
@require_POST
def order_action(request, pk, action):
    order = get_object_or_404(Order, pk=pk)
    if action == "klaar" and order.status == Order.PAID:
        services.mark_ready(order, request.user)
        messages.success(request, f"{order.name} krijgt een mail dat de bestelling klaarligt.")
    elif action == "geleverd" and services.mark_delivered(order, request.user):
        messages.success(request, f"Bestelling {order.number} is geleverd. De stock is bijgewerkt.")
        return redirect("stock:to_deliver")
    elif action == "niet-afgehaald" and services.mark_not_collected(order, request.user):
        messages.success(request, f"Bestelling {order.number} is niet afgehaald. De kledij is weer beschikbaar.")
        return redirect("stock:to_deliver")
    else:
        messages.error(request, "Dat kan niet voor deze bestelling.")
    return redirect("stock:order", pk=order.pk)


@stock_required
def stock_overview(request):
    products = Product.objects.filter(kind=Product.KIND_ARTICLE).prefetch_related("variants")
    return render(request, "stock/stock.html", {"products": products, "tab": "stock"})


REASONS = [
    ("Levering Bioracer", "Levering Bioracer"),
    ("Telling", "Telling (correctie)"),
    ("Beschadigd of verloren", "Beschadigd of verloren"),
    ("Andere", "Andere"),
]


class AdjustForm(forms.Form):
    delta = forms.IntegerField(label="Hoeveel erbij (+) of eraf (−)", min_value=-500, max_value=500)
    reason = forms.ChoiceField(label="Reden", choices=[("", "Kies een reden")] + REASONS)
    detail = forms.CharField(label="Toelichting", required=False, max_length=150)

    def clean(self):
        data = super().clean()
        if data.get("delta") == 0:
            self.add_error("delta", "Geef een aantal verschillend van 0.")
        if data.get("reason") == "Andere" and not data.get("detail"):
            self.add_error("detail", "Geef kort de reden.")
        return data


@stock_required
def adjust(request, pk):
    variant = get_object_or_404(Variant.objects.select_related("product"), pk=pk)
    form = AdjustForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        reason = data["reason"] + (f": {data['detail']}" if data["detail"] else "")
        services.adjust_stock(variant, data["delta"], reason, request.user)
        messages.success(request, f"{variant}: {data['delta']:+d}, nu {variant.stock} in de kast.")
        return redirect("stock:stock")
    movements = variant.movements.select_related("user")[:10]
    return render(request, "stock/adjust.html", {"variant": variant, "form": form, "movements": movements, "tab": "stock"})


@stock_required
def search(request):
    query = request.GET.get("q", "").strip()
    orders = []
    if query:
        orders = Order.objects.filter(
            Q(number__icontains=query) | Q(name__icontains=query) | Q(email__icontains=query) | Q(phone__icontains=query)
        ).exclude(status__in=[Order.PENDING, Order.EXPIRED])[:30]
    return render(request, "stock/search.html", {"query": query, "orders": orders, "tab": "zoeken"})


@stock_required
def log(request):
    movements = StockMovement.objects.select_related("variant__product", "user", "order")[:100]
    return render(request, "stock/log.html", {"movements": movements, "tab": "logboek"})


def manifest(request):
    return JsonResponse(
        {
            "name": "WTC Zonnebeke stock",
            "short_name": "WTC stock",
            "start_url": "/stock/",
            "scope": "/stock/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#231f20",
            "icons": [
                {"src": static("img/icon-192.png"), "sizes": "192x192", "type": "image/png"},
                {"src": static("img/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            ],
        },
        content_type="application/manifest+json",
    )

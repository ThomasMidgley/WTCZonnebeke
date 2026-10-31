import json
import logging

from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import payments, services
from .forms import CheckoutForm
from .models import Order

logger = logging.getLogger(__name__)


@never_cache
def cart_view(request):
    cart = services.Cart(request.session)
    if request.method == "POST":
        try:
            cart.update(int(request.POST.get("index", -1)), int(request.POST.get("qty", 0)))
        except ValueError:
            pass
        return redirect("shop_cart")
    lines = cart.lines()
    return render(request, "shop/cart.html", {"lines": lines, "total": cart.total(lines)})


@never_cache
def checkout_view(request):
    cart = services.Cart(request.session)
    lines = cart.lines()
    if not lines:
        return redirect("shop_cart")
    members_only = any(line["product"].members_only for line in lines)
    has_goods = any(not line["product"].is_event for line in lines)
    form = CheckoutForm(request.POST or None, members_only=members_only, has_goods=has_goods)
    if request.method == "POST" and form.is_valid():
        if not payments.is_configured():
            messages.error(request, "Online betalen is nog niet ingesteld. Probeer het later opnieuw.")
            return redirect("shop_checkout")
        for line in lines:
            left = line["product"].places_left if line["product"].is_event else None
            if left is not None and line["qty"] > left:
                messages.error(request, f"{line['product'].title}: er zijn nog maar {left} plaatsen vrij.")
                return redirect("shop_cart")
        data = form.cleaned_data
        order = services.create_order(lines, data["name"], data["email"], data["phone"], data["note"])
        order_url = request.build_absolute_uri(reverse("shop_order", args=[order.token]))
        try:
            session_id, url = payments.create_checkout_session(
                order, success_url=order_url + "?betaald=1", cancel_url=request.build_absolute_uri(reverse("shop_cart"))
            )
        except Exception:
            logger.exception("Stripe-sessie voor bestelling %s mislukt", order.number)
            services.mark_failed(order)
            messages.error(request, "Betalen lukt even niet. Probeer het binnen enkele minuten opnieuw.")
            return redirect("shop_checkout")
        order.stripe_session_id = session_id
        order.save(update_fields=["stripe_session_id"])
        cart.clear()
        return redirect(url)
    return render(
        request,
        "shop/checkout.html",
        {"form": form, "lines": lines, "total": cart.total(lines), "preorder": any(l["preorder"] for l in lines)},
    )


@never_cache
def order_view(request, token):
    order = get_object_or_404(Order.objects.prefetch_related("lines"), token=token)
    return render(request, "shop/order.html", {"order": order, "just_paid": request.GET.get("betaald")})


@csrf_exempt
@require_POST
def stripe_webhook(request):
    try:
        event = payments.parse_webhook(request.body, request.headers.get("Stripe-Signature"))
    except ValueError:
        return HttpResponseBadRequest("ongeldig")
    event_type = event["type"]
    session = event["data"]["object"]
    order = Order.objects.filter(stripe_session_id=session.get("id")).first()
    if order is None:
        # Bv. een betaling van een andere toepassing op hetzelfde Stripe-account.
        return HttpResponse("onbekend")
    if event_type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        if session.get("payment_status") == "paid":
            services.mark_paid(order, session.get("payment_intent") or "")
    elif event_type == "checkout.session.async_payment_failed":
        services.mark_failed(order, Order.CANCELLED)
    elif event_type == "checkout.session.expired":
        services.mark_failed(order, Order.EXPIRED)
    return HttpResponse(json.dumps({"ok": True}), content_type="application/json")

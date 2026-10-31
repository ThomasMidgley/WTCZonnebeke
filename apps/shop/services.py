"""Bedrijfslogica van de shop: winkelmandje, bestellingen, stock en mails."""

import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import F
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.models import Clubgegevens, Toegang

from .models import Order, OrderLine, Product, StockMovement, Variant

logger = logging.getLogger(__name__)
CART_KEY = "winkelmandje"


# ---------------------------------------------------------------- winkelmandje


class Cart:
    """Winkelmandje in de sessie: [{"product": id, "variants": [id, ...], "qty": n}, ...].

    Een artikel heeft één variant (de gekozen maat), een pakket één variant per onderdeel.
    """

    def __init__(self, session):
        self.session = session
        self.items = list(session.get(CART_KEY, []))

    def save(self):
        self.session[CART_KEY] = self.items
        self.session.modified = True

    def add(self, product, variants, qty=1):
        key = {"product": product.pk, "variants": [v.pk for v in variants]}
        for item in self.items:
            if item["product"] == key["product"] and item["variants"] == key["variants"]:
                item["qty"] = min(item["qty"] + qty, 20)
                break
        else:
            self.items.append({**key, "qty": qty})
        self.save()

    def update(self, index, qty):
        if 0 <= index < len(self.items):
            if qty <= 0:
                self.items.pop(index)
            else:
                self.items[index]["qty"] = min(qty, 20)
            self.save()

    def clear(self):
        self.items = []
        self.save()

    def __len__(self):
        return sum(item["qty"] for item in self.items)

    def lines(self):
        """Het mandje met de objecten erbij. Wat intussen niet meer te koop is, valt weg."""
        products = Product.objects.in_bulk([item["product"] for item in self.items])
        variant_ids = [vid for item in self.items for vid in item["variants"]]
        variants = Variant.objects.select_related("product").in_bulk(variant_ids)
        result = []
        for index, item in enumerate(self.items):
            product = products.get(item["product"])
            chosen = [variants.get(vid) for vid in item["variants"]]
            if not product or not product.is_visible or not chosen or None in chosen:
                continue
            if any(not v.is_active for v in chosen):
                continue
            result.append({
                "index": index,
                "product": product,
                "variants": chosen,
                "qty": item["qty"],
                "total": product.price * item["qty"],
                "preorder": any(v.available < item["qty"] for v in chosen),
            })
        return result

    def total(self, lines=None):
        return sum((line["total"] for line in (lines or self.lines())), Decimal("0"))


# ---------------------------------------------------------------- bestellingen


@transaction.atomic
def create_order(cart_lines, name, email, phone="", note=""):
    order = Order.objects.create(name=name, email=email.strip().lower(), phone=phone, note=note)
    total = Decimal("0")
    for line in cart_lines:
        product, qty = line["product"], line["qty"]
        total += product.price * qty
        if product.is_package:
            # De prijs van het pakket staat op het eerste onderdeel; de andere onderdelen staan op 0.
            for position, variant in enumerate(line["variants"]):
                OrderLine.objects.create(
                    order=order, product=variant.product, variant=variant, package=product,
                    title=f"{product.title}: {variant.product.title}", size=variant.label, quantity=qty,
                    unit_price=product.price if position == 0 else Decimal("0"),
                    is_preorder=variant.available < qty,
                )
        else:
            variant = line["variants"][0]
            OrderLine.objects.create(
                order=order, product=product, variant=variant, title=product.title, size=variant.label,
                quantity=qty, unit_price=product.price, is_preorder=variant.available < qty,
            )
    order.total = total
    order.save(update_fields=["total"])
    return order


def mark_paid(order, payment_intent=""):
    """Na de bevestiging van Stripe. Kan meer dan eens binnenkomen: enkel de eerste keer telt."""
    with transaction.atomic():
        updated = Order.objects.filter(pk=order.pk, status__in=[Order.PENDING, Order.EXPIRED]).update(
            status=Order.PAID, paid_at=timezone.now(), stripe_payment_intent=payment_intent
        )
    if not updated:
        return False
    order.refresh_from_db()
    send_order_mails(order)
    return True


def mark_failed(order, status=Order.CANCELLED):
    Order.objects.filter(pk=order.pk, status=Order.PENDING).update(status=status)


def expire_pending(now=None):
    now = now or timezone.now()
    return Order.objects.filter(status=Order.PENDING, expires_at__lte=now).update(status=Order.EXPIRED)


def mark_ready(order, user):
    order.status = Order.READY
    order.ready_at = timezone.now()
    order.handled_by = user
    order.save(update_fields=["status", "ready_at", "handled_by"])
    send_customer_mail(order, "shop/email/ready.txt", f"Je bestelling {order.number} ligt klaar")


@transaction.atomic
def mark_delivered(order, user):
    if order.status not in Order.OPEN:
        return False
    for line in order.lines.select_related("variant"):
        if line.variant_id:
            adjust_stock(line.variant, -line.quantity, f"Geleverd: bestelling {order.number}", user, order=order)
    order.status = Order.DELIVERED
    order.delivered_at = timezone.now()
    order.handled_by = user
    order.save(update_fields=["status", "delivered_at", "handled_by"])
    return True


def mark_not_collected(order, user):
    """Niet afgehaald: de reservatie vervalt, de kledij is weer beschikbaar voor anderen."""
    if not order.can_mark_not_collected:
        return False
    order.status = Order.NOT_COLLECTED
    order.handled_by = user
    order.save(update_fields=["status", "handled_by"])
    return True


# ---------------------------------------------------------------- stock


@transaction.atomic
def adjust_stock(variant, delta, reason, user=None, order=None):
    Variant.objects.filter(pk=variant.pk).update(stock=F("stock") + delta)
    variant.refresh_from_db(fields=["stock"])
    return StockMovement.objects.create(
        variant=variant, delta=delta, stock_after=variant.stock, reason=reason, user=user, order=order
    )


# ---------------------------------------------------------------- mails


def _context(order):
    return {"order": order, "lines": order.lines.all(), "club": Clubgegevens.load(), "base_url": settings.WAGTAILADMIN_BASE_URL}


def send_customer_mail(order, template, subject):
    try:
        EmailMessage(subject, render_to_string(template, _context(order)), to=[order.email]).send()
    except Exception:
        logger.exception("Mail naar klant voor bestelling %s mislukt", order.number)


def send_order_mails(order):
    send_customer_mail(order, "shop/email/confirmation.txt", f"Bevestiging bestelling {order.number}")
    stock_emails = sorted(Toegang.load().stock_addresses())
    if stock_emails:
        try:
            EmailMessage(
                f"Nieuwe bestelling {order.number}",
                render_to_string("shop/email/new_order.txt", _context(order)),
                to=stock_emails,
                reply_to=[order.email],
            ).send()
        except Exception:
            logger.exception("Mail naar stockbeheer voor bestelling %s mislukt", order.number)

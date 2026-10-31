"""Betalen met Stripe Checkout (de betaalpagina van Stripe zelf).

Welke betaalmethodes de klant ziet (Bancontact, kaart, Apple Pay, Google Pay),
stel je in het Stripe-dashboard in. De sleutels komen enkel uit de omgeving:
STRIPE_SECRET_KEY en STRIPE_WEBHOOK_SECRET.
"""

import stripe
from django.conf import settings

# Stripe vraagt minstens 30 minuten; dat is ook hoe lang we de stock vasthouden.
SESSION_MINUTES = 30


def is_configured():
    return bool(settings.STRIPE_SECRET_KEY)


def client():
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY)


def create_checkout_session(order, success_url, cancel_url):
    line_items = [
        {
            "quantity": line.quantity,
            "price_data": {
                "currency": "eur",
                "unit_amount": int(line.unit_price * 100),
                "product_data": {"name": f"{line.title} ({line.size})" if line.size else line.title},
            },
        }
        for line in order.lines.all()
        if line.unit_price > 0
    ]
    session = client().v1.checkout.sessions.create(
        params={
            "mode": "payment",
            "line_items": line_items,
            "customer_email": order.email,
            "client_reference_id": order.number,
            "metadata": {"order": order.number},
            "payment_intent_data": {"description": f"WTC Zonnebeke bestelling {order.number}"},
            "success_url": success_url,
            "cancel_url": cancel_url,
            "expires_at": int(order.expires_at.timestamp()) + 60,
            "locale": "nl",
        }
    )
    return session.id, session.url


def parse_webhook(payload, signature):
    """Controleert de handtekening van Stripe; geeft het event terug of gooit een ValueError."""
    try:
        return stripe.Webhook.construct_event(payload, signature, settings.STRIPE_WEBHOOK_SECRET)
    except stripe.SignatureVerificationError as exc:
        raise ValueError("ongeldige handtekening") from exc

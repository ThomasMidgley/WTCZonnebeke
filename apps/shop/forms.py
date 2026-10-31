from django import forms
from django.core.validators import RegexValidator

from apps.cyql.models import Member
from apps.formulieren.forms import QuestionsMixin


def variant_choices(product):
    choices = []
    for variant in product.visible_variants():
        hint = " (voorbestelling)" if variant.available <= 0 else ""
        choices.append((str(variant.pk), f"{variant.label}{hint}"))
    return choices


class AddToCartForm(QuestionsMixin, forms.Form):
    """Maat kiezen: één keuze voor een artikel, één per onderdeel voor een pakket.

    Een event heeft geen maten, wel eventueel extra vragen uit de formulierenbouwer.
    """

    qty = forms.IntegerField(label="Aantal", min_value=1, max_value=20, initial=1)

    def __init__(self, product, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.product = product
        if product.is_event:
            self.parts = []
            if product.is_membership:
                self.fields["qty"].widget = forms.HiddenInput()
            else:
                self.fields["qty"].label = "Aantal personen"
        elif product.is_package:
            self.parts = [c.component for c in product.components.select_related("component")]
        else:
            self.parts = [product]
        self.add_questions(product.form.questions.all() if product.is_event and product.form_id else [])
        for index, part in enumerate(self.parts):
            label = part.title if product.is_package else "Maat"
            self.fields[f"variant_{index}"] = forms.ChoiceField(
                label=label, choices=[("", "Kies je maat")] + variant_choices(part)
            )

    def variant_fields(self):
        return [self[f"variant_{index}"] for index in range(len(self.parts))]

    def clean(self):
        data = super().clean()
        if self.product.is_event:
            data = self.clean_questions(data)
            if self.product.is_closed:
                raise forms.ValidationError("De inschrijvingen zijn afgesloten.")
            left = self.product.places_left
            if left is not None and data.get("qty", 1) > left:
                raise forms.ValidationError(
                    "Dit event is volzet." if left == 0 else f"Er zijn nog maar {left} plaatsen vrij."
                )
            if self.product.is_membership:
                data["qty"] = 1
            data["variants"] = []
            return data
        chosen = []
        for index, part in enumerate(self.parts):
            value = data.get(f"variant_{index}")
            variant = next((v for v in part.visible_variants() if str(v.pk) == value), None)
            if value and variant is None:
                self.add_error(f"variant_{index}", "Deze maat is niet meer te koop.")
            chosen.append(variant)
        data["variants"] = chosen
        return data


phone_validator = RegexValidator(r"^[0-9 +/.()-]{9,20}$", "Geef een geldig gsm-nummer.")


class CheckoutForm(forms.Form):
    name = forms.CharField(label="Voor- en achternaam", max_length=120)
    email = forms.EmailField(
        label="E-mailadres", help_text="Leden: gebruik het adres waarmee je in de Cyql-app staat."
    )
    phone = forms.CharField(label="Gsm", max_length=20, validators=[phone_validator])
    note = forms.CharField(label="Opmerking (optioneel)", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    accept = forms.BooleanField(label="Ik haal de kledij af bij de kledijverantwoordelijke na een clubrit of na afspraak.")

    def __init__(self, *args, members_only=False, has_goods=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.members_only = members_only
        if not has_goods:
            self.fields["accept"].label = "Ik ga akkoord met het clubreglement."

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if self.members_only and not Member.is_member(email):
            raise forms.ValidationError(
                "Clubkledij is enkel voor leden en we vinden dit adres niet in de ledenlijst. Gebruik het "
                "e-mailadres waarmee je in de Cyql-app staat, of neem contact op met het bestuur."
            )
        return email

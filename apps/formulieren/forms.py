import requests
from django import forms
from django.conf import settings

from .models import Question, normalize_be_phone, visible_questions

TURNSTILE_VERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def field_for(question):
    common = {"label": question.label, "required": question.required, "help_text": question.help_text}
    kind = question.kind
    if kind == Question.TEXTAREA:
        return forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), max_length=4000, **common)
    if kind == Question.EMAIL:
        return forms.EmailField(**common)
    if kind == Question.PHONE:
        return forms.CharField(max_length=30, widget=forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel"}), **common)
    if kind == Question.DATE:
        return forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"), **common)
    if kind == Question.CHOICE:
        choices = [(c, c) for c in question.choice_list()]
        return forms.ChoiceField(choices=choices, widget=forms.RadioSelect, **common)
    if kind == Question.CHOICES_MULTI:
        choices = [(c, c) for c in question.choice_list()]
        return forms.MultipleChoiceField(choices=choices, widget=forms.CheckboxSelectMultiple, **common)
    return forms.CharField(max_length=500, **common)


class QuestionsMixin:
    """Voegt de vragen van een formulier toe als velden q_0, q_1, ... en volgt de sprongregels."""

    def add_questions(self, questions):
        self.questions = list(questions)
        for index, question in enumerate(self.questions):
            field = field_for(question)
            attrs = field.widget.attrs
            attrs["data-question"] = str(index + 1)
            if question.jump_answer and question.jump_to is not None:
                attrs["data-jump-answer"] = question.jump_answer.strip()
                attrs["data-jump-to"] = str(question.jump_to)
            self.fields[f"q_{index}"] = field
        if self.is_bound:
            # Vragen die door een sprong overgeslagen worden, zijn nooit verplicht.
            raw = {}
            for index, question in enumerate(self.questions):
                key = self.add_prefix(f"q_{index}")
                raw[index] = self.data.getlist(key) if question.kind == Question.CHOICES_MULTI else self.data.get(key)
            self.visible = set(visible_questions(self.questions, raw))
            for index in range(len(self.questions)):
                if index not in self.visible:
                    self.fields[f"q_{index}"].required = False
        else:
            self.visible = set(range(len(self.questions)))

    def question_fields(self):
        return [self[f"q_{index}"] for index in range(len(self.questions))]

    def clean_questions(self, data):
        for index, question in enumerate(self.questions):
            key = f"q_{index}"
            if question.kind == Question.PHONE and index in self.visible and data.get(key):
                phone = normalize_be_phone(data[key])
                if phone is None:
                    self.add_error(key, "Geef een geldig Belgisch nummer, bv. 0470 12 34 56.")
                else:
                    data[key] = phone
        return data

    def answers(self):
        """Lijst van [vraag, antwoord] voor de vragen die de invuller zag."""
        result = []
        for index, question in enumerate(self.questions):
            if index not in self.visible:
                continue
            value = self.cleaned_data.get(f"q_{index}")
            if isinstance(value, list):
                value = ", ".join(value)
            elif hasattr(value, "strftime"):
                value = value.strftime("%d/%m/%Y")
            result.append([question.label, value or ""])
        return result

    def first_email(self):
        for index, question in enumerate(self.questions):
            if question.kind == Question.EMAIL and index in self.visible and self.cleaned_data.get(f"q_{index}"):
                return self.cleaned_data[f"q_{index}"].strip().lower()
        return ""


class PublicForm(QuestionsMixin, forms.Form):
    # Valstrik voor spambots: mensen zien dit veld niet.
    website = forms.CharField(required=False, label="Laat dit veld leeg")

    def __init__(self, form_obj, *args, remote_ip=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.form_obj = form_obj
        self.remote_ip = remote_ip
        self.add_questions(form_obj.questions.all())

    def clean(self):
        data = self.clean_questions(super().clean())
        if data.get("website"):
            raise forms.ValidationError("Er liep iets mis. Probeer opnieuw.")
        if settings.TURNSTILE_SECRET_KEY and not self.turnstile_ok():
            raise forms.ValidationError("Bevestig dat je geen robot bent en probeer opnieuw.")
        if self.form_obj.one_per_email:
            email = self.first_email()
            if email and self.form_obj.submissions.filter(email=email).exists():
                raise forms.ValidationError("Met dit e-mailadres werd dit formulier al ingevuld.")
        return data

    def turnstile_ok(self):
        token = self.data.get("cf-turnstile-response", "")
        if not token:
            return False
        try:
            response = requests.post(
                TURNSTILE_VERIFY,
                data={"secret": settings.TURNSTILE_SECRET_KEY, "response": token, "remoteip": self.remote_ip or ""},
                timeout=10,
            )
            return bool(response.json().get("success"))
        except (requests.RequestException, ValueError):
            return False

"""Stock exporteren naar en importeren uit een csv-bestand.

Eén regel per artikel: artikel; artikelnummer; XS; S; M; L; XL; XXL; XXXL.
Een import overschrijft de stock van elke maat op de regel; een lege cel telt als 0.
Artikels die niet in het bestand staan, blijven ongewijzigd.
"""

import csv
import io
from collections import Counter
from dataclasses import dataclass, field

from django.db import transaction

from . import services
from .models import SIZES, Product, Variant

HEADER = ["artikel", "artikelnummer", *SIZES]
CATEGORY_ORDER = [key for key, _ in Product.ARTICLE_CATEGORIES]


@dataclass
class Group:
    """Een rij in de csv: de maten van één artikel."""

    product: Product
    name: str
    variants: dict = field(default_factory=dict)

    @property
    def number(self):
        return self.product.article_number


def groups():
    """Per categorie (Algemeen, Dames, Heren). Bestaat dezelfde naam in meer categorieën, dan staat die erbij."""
    products = sorted(
        Product.objects.filter(kind=Product.KIND_ARTICLE).prefetch_related("variants"),
        key=lambda p: (CATEGORY_ORDER.index(p.category), p.sort_order, p.title),
    )
    counts = Counter(product.title.casefold() for product in products)
    result = []
    for product in products:
        name = product.title
        if counts[name.casefold()] > 1 and product.category_label:
            name = f"{product.title} ({product.category_label.lower()})"
        result.append(Group(product, name, {v.size.upper(): v for v in product.variants.all()}))
    return result


def export_csv():
    buffer = io.StringIO()
    buffer.write("﻿")  # zodat Excel de accenten juist toont
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(HEADER)
    for group in groups():
        writer.writerow(
            [group.name, group.number, *[group.variants[size].stock if size in group.variants else "" for size in SIZES]]
        )
    return buffer.getvalue()


def decode(raw):
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Het bestand kon niet gelezen worden. Bewaar het als csv (UTF-8).")


class StockImportError(Exception):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def parse(text):
    """Geeft [(group, {maat: aantal})] terug, of StockImportError met alle fouten (dan verandert er niets)."""
    dialect = ";" if text.split("\n", 1)[0].count(";") >= text.split("\n", 1)[0].count(",") else ","
    rows = [row for row in csv.reader(io.StringIO(text), delimiter=dialect) if any(cell.strip() for cell in row)]
    if not rows:
        raise StockImportError(["Het bestand is leeg."])
    header = [cell.strip().upper() for cell in rows[0]]
    size_columns = {index: size for index, size in enumerate(header) if index >= 2 and size}
    unknown = [size for size in size_columns.values() if size not in SIZES]
    if len(header) < 3 or unknown:
        raise StockImportError(
            [f"De eerste regel moet zijn: {';'.join(HEADER)}" + (f" (onbekende maat: {', '.join(unknown)})" if unknown else "")]
        )

    all_groups = groups()
    by_name = {group.name.casefold(): group for group in all_groups}
    by_number = {}
    for group in all_groups:
        if group.number:
            by_number.setdefault(group.number.casefold(), []).append(group)

    errors, result, seen = [], [], set()
    for line, row in enumerate(rows[1:], start=2):
        row = row + [""] * (len(header) - len(row))
        name, number = row[0].strip(), row[1].strip()
        group = by_name.get(name.casefold())
        if not group and len(by_number.get(number.casefold(), [])) == 1:
            group = by_number[number.casefold()][0]
        if not group:
            errors.append(f"regel {line}: artikel '{name}' ({number}) niet gevonden")
            continue
        if id(group) in seen:
            errors.append(f"regel {line}: '{group.name}' staat meer dan eens in het bestand")
            continue
        seen.add(id(group))
        counts = {}
        for index, size in size_columns.items():
            value = row[index].strip()
            try:
                count = int(value) if value else 0
            except ValueError:
                errors.append(f"regel {line}, maat {size}: '{value}' is geen geheel getal")
                continue
            if count < 0:
                errors.append(f"regel {line}, maat {size}: negatieve stock")
            elif size not in group.variants:
                if count:
                    errors.append(f"regel {line}: '{group.name}' heeft geen maat {size}")
            else:
                counts[size] = count
        result.append((group, counts))
    if errors:
        raise StockImportError(errors)
    return result


def import_csv(raw, user=None):
    """Overschrijft de stock. Geeft (aantal gewijzigde maten, namen van artikels die niet in het bestand stonden)."""
    parsed = parse(decode(raw))
    changed = 0
    with transaction.atomic():
        for group, counts in parsed:
            for size, count in counts.items():
                variant = Variant.objects.select_for_update().get(pk=group.variants[size].pk)
                if variant.stock != count:
                    services.adjust_stock(variant, count - variant.stock, "Import csv", user)
                    changed += 1
    imported = {group.name for group, _ in parsed}
    missing = [group.name for group in groups() if group.name not in imported]
    return changed, missing

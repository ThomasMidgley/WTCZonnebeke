"""
Toont welke gegevens de Cyql-API aanbiedt (het GraphQL-schema).

Gebruik in de Portainer-console van de container:  python manage.py cyql_schema
De uitvoer bevat geen API-sleutel en mag gedeeld worden.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.cyql.client import CyqlClient, CyqlError

TYPES_QUERY = "{ __schema { queryType { name } types { name kind } } }"


def type_ref(levels):
    """Selectie voor een type, met `levels` keer ofType (voor lijsten en verplichte velden)."""
    return "kind name" + (f" ofType {{ {type_ref(levels - 1)} }}" if levels > 0 else "")


def type_query(levels, with_args):
    ref = type_ref(levels)
    args = f" args {{ name type {{ {ref} }} }}" if with_args else ""
    return (
        "query($name: String!) { __type(name: $name) { name kind description "
        f"fields {{ name{args} type {{ {ref} }} }} "
        f"inputFields {{ name type {{ {ref} }} }} enumValues {{ name }} }} }}"
    )


# Van volledig naar minimaal: Cyql begrenst de diepte van een vraag.
VARIANTS = [(levels, True) for levels in (3, 2, 1, 0)] + [(levels, False) for levels in (3, 2, 1, 0)]


def type_name(ref):
    # Ontbreekt ofType (te weinig diepte toegelaten), dan tonen we "…".
    if ref is None:
        return "…"
    if ref["kind"] == "NON_NULL":
        return type_name(ref.get("ofType")) + "!"
    if ref["kind"] == "LIST":
        return f"[{type_name(ref.get('ofType'))}]"
    return ref["name"]


def render_type(t):
    keyword = {"OBJECT": "type", "INPUT_OBJECT": "input", "ENUM": "enum", "INTERFACE": "interface"}.get(
        t["kind"], t["kind"].lower()
    )
    lines = [f'"""{t["description"]}"""'] if t.get("description") else []
    lines.append(f"{keyword} {t['name']} {{")
    for field in t.get("fields") or []:
        args = ", ".join(f"{a['name']}: {type_name(a['type'])}" for a in field.get("args") or [])
        lines.append(f"  {field['name']}{f'({args})' if args else ''}: {type_name(field['type'])}")
    for field in t.get("inputFields") or []:
        lines.append(f"  {field['name']}: {type_name(field['type'])}")
    for value in t.get("enumValues") or []:
        lines.append(f"  {value['name']}")
    lines.append("}")
    return "\n".join(lines)


class Command(BaseCommand):
    help = "Toont het GraphQL-schema van de Cyql-API."

    def handle(self, *args, **options):
        client = CyqlClient()
        try:
            schema = client.query(TYPES_QUERY)["__schema"]
            names = [
                t["name"]
                for t in schema["types"]
                if not t["name"].startswith("__") and t["kind"] in ("OBJECT", "INPUT_OBJECT", "ENUM", "INTERFACE")
            ]
            # Querytype eerst, daarna alfabetisch.
            query_type = schema["queryType"]["name"]
            names.sort(key=lambda n: (n != query_type, n))
            query = None
            for name in names:
                if query is None:
                    query, t = self.find_query(client, name)
                else:
                    t = client.query(query, {"name": name})["__type"]
                self.stdout.write(render_type(t) + "\n")
        except CyqlError as exc:
            raise CommandError(f"Cyql gaf een fout: {exc.code}: {exc}") from exc
        if client.remaining is not None:
            self.stdout.write(f"# Resterend weekbudget van de club: {client.remaining}")

    def find_query(self, client, name):
        """Zoekt de meest volledige vraag die Cyql nog toelaat."""
        for levels, with_args in VARIANTS:
            query = type_query(levels, with_args)
            try:
                result = client.query(query, {"name": name})["__type"]
            except CyqlError as exc:
                if exc.code == "ExceedingMaxDepth":
                    continue
                raise
            note = "" if with_args else ", zonder argumenten"
            self.stdout.write(f"# Diepte: {levels} niveaus{note}\n")
            return query, result
        raise CyqlError("Zelfs de kleinste vraag is te diep", code="ExceedingMaxDepth")

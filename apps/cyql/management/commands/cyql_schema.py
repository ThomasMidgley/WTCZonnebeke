"""
Toont welke gegevens de Cyql-API aanbiedt (het GraphQL-schema).

Gebruik in de Portainer-console van de container:  python manage.py cyql_schema
De uitvoer bevat geen API-sleutel en mag gedeeld worden.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.cyql.client import CyqlClient, CyqlError

TYPE_REF = "kind name ofType { kind name ofType { kind name ofType { kind name } } }"
TYPES_QUERY = "{ __schema { queryType { name } types { name kind } } }"
TYPE_QUERY = (
    "query($name: String!) { __type(name: $name) { name kind description "
    f"fields {{ name description args {{ name type {{ {TYPE_REF} }} }} type {{ {TYPE_REF} }} }} "
    f"inputFields {{ name type {{ {TYPE_REF} }} }} enumValues {{ name }} }} }}"
)


def type_name(ref):
    if ref is None:
        return "?"
    if ref["kind"] == "NON_NULL":
        return type_name(ref["ofType"]) + "!"
    if ref["kind"] == "LIST":
        return f"[{type_name(ref['ofType'])}]"
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
            for name in names:
                t = client.query(TYPE_QUERY, {"name": name})["__type"]
                self.stdout.write(render_type(t) + "\n")
        except CyqlError as exc:
            raise CommandError(f"Cyql gaf een fout: {exc.code}: {exc}") from exc
        if client.remaining is not None:
            self.stdout.write(f"# Resterend weekbudget van de club: {client.remaining}")

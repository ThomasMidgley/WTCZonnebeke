import datetime
import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import CyqlApp

from .client import CyqlClient, CyqlError
from .management.commands.cyql_schema import Command as SchemaCommand
from .management.commands.cyql_schema import render_type, type_name
from .models import Challenge, ClubEvent, ClubStats, Member, Ride, SyncRun
from .scheduler import sync_due
from .sync import MAX_PAGES, fetch_all, run_sync


def fake_response(body, status=200, headers=None):
    response = mock.Mock(status_code=status, headers=headers or {})
    response.json.return_value = body
    return response


@override_settings(CYQL_API_KEY="test-key", CYQL_API_URL="https://cyql.test/api/graphql")
class ClientTests(TestCase):
    def test_sends_key_and_reads_budget(self):
        body = {"data": {"clubStats": {"memberCount": 120}}}
        with mock.patch("apps.cyql.client.requests.post") as post:
            post.return_value = fake_response(body, headers={"X-RateLimit-Remaining-Club": "950"})
            client = CyqlClient()
            self.assertEqual(client.query("{ clubStats { memberCount } }"), body["data"])
        self.assertEqual(post.call_args.kwargs["headers"]["X-Api-Key"], "test-key")
        self.assertEqual(client.remaining, 950)

    def test_graphql_error_is_raised_with_code(self):
        body = {"errors": [{"message": "ApiKeyInvalid", "extensions": {"code": "ApiKeyInvalid"}}]}
        with mock.patch("apps.cyql.client.requests.post", return_value=fake_response(body, status=401)):
            with self.assertRaises(CyqlError) as ctx:
                CyqlClient().query("{ x }")
        self.assertEqual(ctx.exception.code, "ApiKeyInvalid")

    @override_settings(CYQL_API_KEY="")
    def test_missing_key(self):
        with self.assertRaises(CyqlError) as ctx:
            CyqlClient().query("{ x }")
        self.assertEqual(ctx.exception.code, "NoApiKey")


RIDE_ID = "11111111-1111-1111-1111-111111111111"
EVENT_ID = "22222222-2222-2222-2222-222222222222"
CHALLENGE_ID = "33333333-3333-3333-3333-333333333333"
HIDDEN_ID = "44444444-4444-4444-4444-444444444444"


def fake_cyql(query, variables=None):
    """Antwoorden zoals Cyql ze geeft, gekozen op basis van de vraag."""
    page = (variables or {}).get("page", 1)
    if "clubStats" in query:
        return {"clubStats": {"memberCount": 87}}
    if "rides(" in query:
        return {"rides": {"items": [{
            "id": RIDE_ID, "title": "Zondagsrit", "startTime": "2099-11-08T08:00:00Z", "location": "Markt Zonnebeke",
            "distance": 82.4, "averageSpeed": 27.5, "rideType": "TOUR", "shareUrl": "https://cyql.app/r/1",
            "gpxUrl": "https://storage.cyql.test/route.gpx", "labels": [{"title": "B-ploeg"}, {"title": "27 km/u"}],
        }], "hasNextPage": False}}
    if "events(" in query:
        return {"events": {"items": [{
            "id": EVENT_ID, "title": "Algemene vergadering", "startDateTime": "2099-11-20T19:30:00Z",
            "endTime": None, "location": "Clublokaal",
        }], "hasNextPage": False}}
    if "challenges(" in query:
        return {"challenges": {"items": [
            {"id": CHALLENGE_ID, "title": "Klassement 2026", "scoreType": "SCORE", "startDate": None,
             "endDate": None, "participantCount": 2},
            {"id": HIDDEN_ID, "title": "Kilometers", "scoreType": "DISTANCE", "startDate": None,
             "endDate": None, "participantCount": 2},
        ], "hasNextPage": False}}
    if "challengeScores(" in query:
        return {"challengeScores": {"items": [
            {"memberName": "Jan Peeters", "score": 24, "rank": 1, "rideCount": 24},
            {"memberName": "An De Smet", "score": 20, "rank": 2, "rideCount": 20},
        ], "hasNextPage": False}}
    if "members(" in query:
        items = [{"id": f"55555555-5555-5555-5555-55555555555{page}", "firstName": "Jan", "lastName": f"Lid{page}",
                  "email": f"Jan{page}@Example.be ", "status": "APPROVED"}]
        return {"members": {"items": items, "hasNextPage": page < 2}}
    raise AssertionError(query)


class SyncTests(TestCase):
    def client_mock(self):
        client = mock.Mock(remaining=4700)
        client.query.side_effect = fake_cyql
        return client

    def test_full_sync(self):
        Challenge.objects.create(cyql_id=HIDDEN_ID, title="Kilometers", show_on_site=False)
        run = run_sync(self.client_mock())
        self.assertTrue(run.ok, run.message)
        self.assertEqual(ClubStats.load().member_count, 87)
        ride = Ride.objects.get()
        self.assertEqual(ride.label_list, ["B-ploeg", "27 km/u"])
        self.assertEqual(ClubEvent.objects.get().title, "Algemene vergadering")
        shown = Challenge.objects.get(cyql_id=CHALLENGE_ID)
        self.assertEqual([s.short_name for s in shown.scores.all()], ["Jan P.", "An D."])
        self.assertFalse(Challenge.objects.get(cyql_id=HIDDEN_ID).show_on_site)
        self.assertEqual(Member.objects.count(), 2)
        self.assertTrue(Member.is_member("jan2@example.be"))
        self.assertFalse(Member.is_member("vreemde@example.be"))
        self.assertEqual(run.remaining_budget, 4700)

    def test_scores_query_uses_non_null_uuid(self):
        # Cyql weigert de vraag als het type van $id niet exact UUID! is.
        from .sync import SCORES_QUERY

        self.assertIn("$id: UUID!", SCORES_QUERY)

    def test_hidden_challenge_costs_no_budget(self):
        Challenge.objects.create(cyql_id=HIDDEN_ID, title="Kilometers", show_on_site=False)
        client = self.client_mock()
        run_sync(client)
        asked = [c.args[1]["id"] for c in client.query.call_args_list if "challengeScores" in c.args[0]]
        self.assertEqual(asked, [CHALLENGE_ID])

    def test_resync_replaces_rides(self):
        run_sync(self.client_mock())
        run_sync(self.client_mock())
        self.assertEqual(Ride.objects.count(), 1)

    def test_challenge_missing_from_cyql_is_hidden(self):
        Challenge.objects.create(cyql_id="66666666-6666-6666-6666-666666666666", title="Oud")
        run_sync(self.client_mock())
        self.assertFalse(Challenge.objects.get(title="Oud").is_active)

    def test_failed_sync_is_logged(self):
        client = mock.Mock(remaining=None)
        client.query.side_effect = CyqlError("weg", code="Network")
        run = run_sync(client)
        self.assertFalse(run.ok)
        self.assertIn("Network", run.message)

    def test_budget_error_stops_sync(self):
        client = mock.Mock(remaining=0)
        client.query.side_effect = CyqlError("op", code="ExceedingComplexityBudget")
        run = run_sync(client)
        self.assertEqual(client.query.call_count, 1)
        self.assertEqual(run.message.count("\n"), 0)

    def test_page_limit(self):
        client = mock.Mock(remaining=None)
        client.query.return_value = {"members": {"items": [], "hasNextPage": True}}
        self.assertEqual(fetch_all(client, "q", "members"), [])
        self.assertEqual(client.query.call_count, MAX_PAGES)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class PageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_site", verbosity=0)
        client = mock.Mock(remaining=None)
        client.query.side_effect = fake_cyql
        run_sync(client)

    def test_calendar_shows_rides_and_events(self):
        html = self.client.get("/kalender/").content.decode()
        self.assertIn("Zondagsrit", html)
        self.assertIn("82 km", html)
        self.assertIn("B-ploeg", html)
        self.assertIn('href="https://cyql.app/r/1"', html)
        self.assertIn("Algemene vergadering", html)
        self.assertLess(html.index("Zondagsrit"), html.index("Algemene vergadering"))

    def test_gpx_is_downloaded_as_file(self):
        html = self.client.get("/kalender/").content.decode()
        self.assertIn(f'href="/gpx/{RIDE_ID}/" download', html)
        upstream = mock.Mock()
        upstream.raw.read.return_value = b"<gpx></gpx>"
        with mock.patch("apps.cyql.views.requests.get", return_value=upstream) as get:
            response = self.client.get(f"/gpx/{RIDE_ID}/")
        get.assert_called_once_with("https://storage.cyql.test/route.gpx", timeout=15, stream=True)
        self.assertEqual(response["Content-Type"], "application/gpx+xml")
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="2099-11-08-zondagsrit.gpx"')
        self.assertEqual(response.content, b"<gpx></gpx>")

    def test_gpx_of_unknown_ride_is_404(self):
        self.assertEqual(self.client.get("/gpx/99999999-9999-9999-9999-999999999999/").status_code, 404)

    def test_event_links_to_cyql_page_by_default(self):
        html = self.client.get("/kalender/").content.decode()
        self.assertIn('<a href="/cyql/">Bekijk in Cyql</a>', html)

    def test_event_link_from_settings(self):
        from apps.core.models import CyqlApp

        cyql = CyqlApp.load()
        cyql.event_url = "https://cyql.test/event/{id}"
        cyql.save()
        html = self.client.get("/kalender/").content.decode()
        self.assertIn(f'href="https://cyql.test/event/{EVENT_ID}" rel="noopener">Bekijk in Cyql', html)

    def test_past_rides_are_hidden(self):
        Ride.objects.update(start_time=timezone.now() - datetime.timedelta(hours=1))
        self.assertNotIn("Zondagsrit", self.client.get("/kalender/").content.decode())

    def test_hidden_challenge_not_on_page(self):
        Challenge.objects.filter(cyql_id=HIDDEN_ID).update(show_on_site=False)
        self.assertNotIn("Kilometers", self.client.get("/klassement/").content.decode())

    def test_ranking_shows_short_names_by_default(self):
        html = self.client.get("/klassement/").content.decode()
        self.assertIn("Klassement 2026", html)
        self.assertIn("Jan P.", html)
        self.assertNotIn("Peeters", html)

    def test_ranking_full_names_option(self):
        from apps.pages.models import RankingPage

        page = RankingPage.objects.get()
        page.show_full_names = True
        page.save_revision().publish()
        self.assertIn("Jan Peeters", self.client.get("/klassement/").content.decode())


class SchedulerTests(TestCase):
    def setUp(self):
        cyql = CyqlApp.load()
        cyql.sync_time = datetime.time(3, 0)
        cyql.save()

    def at(self, hour, minute=0):
        return timezone.make_aware(datetime.datetime(2026, 11, 2, hour, minute))

    def test_not_due_before_time(self):
        self.assertFalse(sync_due(self.at(2, 59)))

    def test_due_after_time_once_per_day(self):
        self.assertTrue(sync_due(self.at(3, 1)))
        with mock.patch("django.utils.timezone.now", return_value=self.at(3, 1)):
            SyncRun.objects.create(ok=True)
        self.assertFalse(sync_due(self.at(14, 0)))

    def test_run_from_yesterday_does_not_count(self):
        with mock.patch("django.utils.timezone.now", return_value=self.at(3, 1) - datetime.timedelta(days=1)):
            SyncRun.objects.create(ok=True)
        self.assertTrue(sync_due(self.at(3, 5)))


class SchemaRenderTests(TestCase):
    def test_render_object_type(self):
        t = {
            "name": "Query",
            "kind": "OBJECT",
            "description": None,
            "fields": [
                {
                    "name": "rides",
                    "args": [{"name": "pageSize", "type": {"kind": "SCALAR", "name": "Int", "ofType": None}}],
                    "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "OBJECT", "name": "RidePage", "ofType": None}},
                }
            ],
            "inputFields": None,
            "enumValues": None,
        }
        self.assertEqual(render_type(t), "type Query {\n  rides(pageSize: Int): RidePage!\n}")


    def test_truncated_type_is_marked(self):
        self.assertEqual(type_name({"kind": "NON_NULL", "name": None}), "…!")

    def test_schema_falls_back_to_shallower_query(self):
        def answer(query, variables=None):
            if "__schema" in query:
                return {"__schema": {"queryType": {"name": "Query"}, "types": [{"name": "Query", "kind": "OBJECT"}]}}
            if query.count("ofType") > 3:  # meer dan 1 niveau
                raise CyqlError("ExceedingMaxDepth", code="ExceedingMaxDepth")
            return {"__type": {"name": "Query", "kind": "OBJECT", "fields": [], "inputFields": None, "enumValues": None}}

        client = mock.Mock(remaining=None)
        client.query.side_effect = answer
        out = io.StringIO()
        with mock.patch("apps.cyql.management.commands.cyql_schema.CyqlClient", return_value=client):
            call_command(SchemaCommand(), stdout=out)
        self.assertIn("# Diepte: 1 niveaus", out.getvalue())
        self.assertIn("type Query {", out.getvalue())


class AdminTests(TestCase):
    def test_sync_log_is_visible_for_admin(self):
        SyncRun.objects.create(ok=True, message="clubcijfers: 87 leden")
        user = get_user_model().objects.create_superuser("beheer", "beheer@example.be", "x" * 12)
        self.client.force_login(user)
        response = self.client.get("/admin/cyql_sync/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "87 leden")
        self.assertEqual(self.client.get("/admin/cyql_sync/new/").status_code, 302)

    def test_member_list_is_read_only_and_admin_only(self):
        Member.objects.create(cyql_id=RIDE_ID, first_name="Jan", last_name="Peeters", email="jan@example.be")
        admin = get_user_model().objects.create_superuser("beheer", "beheer@example.be", "x" * 12)
        self.client.force_login(admin)
        self.assertContains(self.client.get("/admin/cyql_members/"), "jan@example.be")
        self.assertEqual(self.client.get("/admin/cyql_members/new/").status_code, 302)

    def test_cyql_menu_sits_between_reports_and_settings(self):
        admin = get_user_model().objects.create_superuser("beheer", "beheer@example.be", "x" * 12)
        self.client.force_login(admin)
        html = self.client.get("/admin/").content.decode()
        self.assertLess(html.index('"name": "reports"'), html.index('"name": "cyql"'))
        self.assertLess(html.index('"name": "cyql"'), html.index('"name": "settings"'))
        self.assertIn("/admin/settings/core/cyqlapp/", html)
        self.assertEqual(html.count("/admin/settings/core/cyqlapp/"), 1)
        response = self.client.get("/admin/settings/core/cyqlapp/", follow=True)
        self.assertContains(response, "Synchroniseren om")

    def test_sync_now_requires_superuser(self):
        from apps.accounts.roles import apply_role

        user = get_user_model().objects.create_user("stock", "stock@example.be", "x" * 12)
        apply_role(user, "stockbeheerder")
        self.client.force_login(user)
        # Wagtail stuurt wie geen rechten heeft terug naar het dashboard.
        with mock.patch("apps.cyql.views.run_sync") as sync:
            response = self.client.post("/admin/cyql/nu-synchroniseren/")
        self.assertRedirects(response, "/admin/", fetch_redirect_response=False)
        sync.assert_not_called()

    def test_sync_now_runs_sync(self):
        admin = get_user_model().objects.create_superuser("beheer", "beheer@example.be", "x" * 12)
        self.client.force_login(admin)
        self.assertContains(self.client.get("/admin/cyql/nu-synchroniseren/"), "Nu synchroniseren")
        with mock.patch("apps.cyql.views.run_sync") as sync:
            sync.return_value = SyncRun(ok=True)
            response = self.client.post("/admin/cyql/nu-synchroniseren/")
        self.assertRedirects(response, "/admin/cyql_sync/", fetch_redirect_response=False)
        sync.assert_called_once()

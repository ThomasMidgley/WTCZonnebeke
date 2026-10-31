import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import Integraties

from .client import CyqlClient, CyqlError
from .management.commands.cyql_schema import render_type
from .models import ClubStats, SyncRun
from .scheduler import sync_due
from .sync import run_sync


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


class SyncTests(TestCase):
    def test_sync_stores_member_count_and_log(self):
        client = mock.Mock(remaining=900)
        client.query.return_value = {"clubStats": {"memberCount": 87}}
        run = run_sync(client)
        self.assertTrue(run.ok)
        self.assertEqual(ClubStats.load().member_count, 87)
        self.assertEqual(run.remaining_budget, 900)

    def test_failed_sync_is_logged(self):
        client = mock.Mock(remaining=None)
        client.query.side_effect = CyqlError("weg", code="Network")
        run = run_sync(client)
        self.assertFalse(run.ok)
        self.assertIn("Network", run.message)


class SchedulerTests(TestCase):
    def setUp(self):
        integraties = Integraties.load()
        integraties.cyql_sync_time = datetime.time(3, 0)
        integraties.save()

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


class AdminTests(TestCase):
    def test_sync_log_is_visible_for_admin(self):
        SyncRun.objects.create(ok=True, message="clubcijfers: 87 leden")
        user = get_user_model().objects.create_superuser("beheer", "beheer@example.be", "x" * 12)
        self.client.force_login(user)
        response = self.client.get("/admin/cyql_sync/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "87 leden")
        self.assertEqual(self.client.get("/admin/cyql_sync/new/").status_code, 302)

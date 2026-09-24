import datetime
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from graphene import Schema
from graphene.test import Client

from core.models import MutationLog
from core.models.openimis_graphql_test_case import BaseTestContext
from core.schema import signal_mutation_module_before_mutating
from core.test_helpers import create_test_interactive_user
from kobo_etl.apps import RUN_ETL_MUTATION_LOG_TAG
from kobo_etl.gql_queries import KoboETLStatusType
from kobo_etl.schema import Mutation, Query, RunKoboETLMutation, bind_signals
from kobo_etl.strategy.kobo_client import KoboFetchError

STATUS_QUERY = "{ koboEtlStatus { lastSyncDate } }"
RUN_MUTATION = """
mutation {
  runKoboEtl(input: {clientMutationId: "%s", scope: GRIEVANCE}) { clientMutationId }
}
"""


def _mutation_log(status, json_ext=None, request_date_time=None):
    log = MutationLog.objects.create(json_content="{}", status=status, json_ext=json_ext)
    if request_date_time is not None:
        MutationLog.objects.filter(id=log.id).update(request_date_time=request_date_time)
    return log


class LastSyncDateResolverTest(TestCase):
    def test_no_etl_run_returns_none(self):
        _mutation_log(MutationLog.SUCCESS)

        self.assertIsNone(KoboETLStatusType().resolve_last_sync_date(None))

    def test_returns_latest_successful_etl_run(self):
        now = timezone.now()
        _mutation_log(MutationLog.SUCCESS, RUN_ETL_MUTATION_LOG_TAG, now - datetime.timedelta(days=3))
        expected = now - datetime.timedelta(days=2)
        _mutation_log(MutationLog.SUCCESS, RUN_ETL_MUTATION_LOG_TAG, expected)
        _mutation_log(MutationLog.ERROR, RUN_ETL_MUTATION_LOG_TAG, now - datetime.timedelta(days=1))
        _mutation_log(MutationLog.SUCCESS, {"mutation_class": "OtherMutation"}, now)
        _mutation_log(MutationLog.SUCCESS, None, now)

        self.assertEqual(KoboETLStatusType().resolve_last_sync_date(None), expected)


class RunKoboETLMutationLogTagTest(TestCase):
    def setUp(self):
        bind_signals()

    def _send(self, log, mutation_class):
        signal_mutation_module_before_mutating["kobo_etl"].send(
            sender=RunKoboETLMutation, mutation_log_id=log.id, data={}, user=None,
            mutation_module="kobo_etl", mutation_class=mutation_class,
        )
        log.refresh_from_db()

    def test_run_etl_mutation_log_is_tagged(self):
        log = _mutation_log(MutationLog.RECEIVED, {"kept": 1})

        self._send(log, "RunKoboETLMutation")

        self.assertEqual(log.json_ext, {"kept": 1, **RUN_ETL_MUTATION_LOG_TAG})
        self.assertEqual(log.status, MutationLog.RECEIVED)

    def test_other_mutation_log_is_not_tagged(self):
        log = _mutation_log(MutationLog.RECEIVED)

        self._send(log, "OtherMutation")

        self.assertIsNone(log.json_ext)


@patch("core.async_mutations", False)
class LastSyncDateGraphQLTest(TestCase):
    """runKoboEtl then koboEtlStatus through the module's GraphQL schema."""

    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_interactive_user(username="kobo_etl_admin")

    def setUp(self):
        bind_signals()
        self.client = Client(Schema(query=Query, mutation=Mutation))

    def _execute(self, payload):
        return self.client.execute(payload, context=BaseTestContext(self.user).get_request())

    def _last_sync_date(self):
        result = self._execute(STATUS_QUERY)
        self.assertNotIn("errors", result)
        return result["data"]["koboEtlStatus"]["lastSyncDate"]

    @patch("kobo_etl.services.KoboServices.get")
    def test_successful_run_sets_last_sync_date(self, kobo_get):
        kobo_get.return_value = {"count": 0, "results": []}
        self.assertIsNone(self._last_sync_date())

        self._execute(RUN_MUTATION % "kobo-etl-ok")

        log = MutationLog.objects.get(client_mutation_id="kobo-etl-ok")
        self.assertEqual(log.status, MutationLog.SUCCESS)
        self.assertEqual(self._last_sync_date(), log.request_date_time.isoformat())

    @patch("kobo_etl.services.KoboServices.get")
    def test_failed_run_is_an_error_and_leaves_last_sync_date_empty(self, kobo_get):
        kobo_get.side_effect = KoboFetchError("KoBo down")

        self._execute(RUN_MUTATION % "kobo-etl-ko")

        log = MutationLog.objects.get(client_mutation_id="kobo-etl-ko")
        self.assertEqual(log.status, MutationLog.ERROR)
        self.assertIn("KoBo down", log.error)
        self.assertIsNone(self._last_sync_date())

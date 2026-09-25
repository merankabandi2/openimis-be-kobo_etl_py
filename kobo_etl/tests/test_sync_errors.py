from unittest.mock import Mock, patch

import requests
from django.test import TestCase

from kobo_etl.schema import RunKoboETLMutation
from kobo_etl.services import KoboServices
from kobo_etl.strategy import kobo_client
from kobo_etl.strategy.kobo_client import KoboFetchError

V1_FORM = "aeAgbxjy7d6rD8jtUdMD9Z"
V2_FORM = "atpoVbHXZCdLD9ETHTv6z4"


def _page(results, next_url=None, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = {"count": 3, "next": next_url, "results": results}
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"{status_code} error", response=response,
        )
    else:
        response.raise_for_status.return_value = None
    return response


def _mock_user():
    user = Mock()
    user.id = 1
    user.username = "test-user"
    user.has_perms.return_value = True
    return user


class KoboClientGetTest(TestCase):
    """kobo_client.get returns every page or raises; it never returns a partial result set."""

    @patch("kobo_etl.strategy.kobo_client.requests.get")
    def test_all_pages_are_returned(self, requests_get):
        requests_get.side_effect = [
            _page([{"_id": 1}], next_url="https://kobo.test/page2"),
            _page([{"_id": 2}, {"_id": 3}]),
        ]

        data = kobo_client.get("form")

        self.assertEqual(data, {"count": 3, "results": [{"_id": 1}, {"_id": 2}, {"_id": 3}]})

    @patch("kobo_etl.strategy.kobo_client.requests.get")
    def test_network_error_on_second_page_raises(self, requests_get):
        requests_get.side_effect = [
            _page([{"_id": 1}], next_url="https://kobo.test/page2"),
            requests.exceptions.ConnectionError("connection reset"),
        ]

        with self.assertRaises(KoboFetchError) as ctx:
            kobo_client.get("form")
        self.assertIn("after 1 submissions", str(ctx.exception))

    @patch("kobo_etl.strategy.kobo_client.requests.get")
    def test_http_error_raises(self, requests_get):
        requests_get.return_value = _page([], status_code=500)

        with self.assertRaises(KoboFetchError):
            kobo_client.get("form")

    @patch("kobo_etl.strategy.kobo_client.requests.get")
    def test_http_409_raises_fetch_error(self, requests_get):
        requests_get.return_value = _page([], status_code=409)

        with self.assertRaises(KoboFetchError):
            kobo_client.get("form")


class SyncGrievanceFailureTest(TestCase):
    """sync_grievance raises when either grievance form fails, after attempting both."""

    @patch("kobo_etl.services.KoboServices.get")
    def test_kobo_unreachable_raises_and_tries_both_forms(self, kobo_get):
        kobo_get.side_effect = KoboFetchError("KoBo down")

        with self.assertRaises(KoboServices.KoboSyncError) as ctx:
            KoboServices.sync_grievance(None, None)

        self.assertEqual([c.args[0] for c in kobo_get.call_args_list], [V1_FORM, V2_FORM])
        self.assertIn("v1: KoBo down", str(ctx.exception))
        self.assertIn("v2: KoBo down", str(ctx.exception))

    @patch("merankabandi.converters.grievance_converter_v2.GrievanceConverterV2.import_batch")
    @patch("kobo_etl.services.KoboServices.get")
    def test_v2_import_error_raises(self, kobo_get, import_batch):
        kobo_get.side_effect = lambda uid: {"count": 1, "results": [{"_id": 1}]} if uid == V2_FORM \
            else {"count": 0, "results": []}
        import_batch.side_effect = RuntimeError("bad row")

        with self.assertRaises(KoboServices.KoboSyncError) as ctx:
            KoboServices.sync_grievance(None, None)

        self.assertIn("v2: bad row", str(ctx.exception))
        self.assertNotIn("v1:", str(ctx.exception))

    @patch("kobo_etl.services.KoboServices.get")
    def test_empty_forms_succeed(self, kobo_get):
        kobo_get.return_value = {"count": 0, "results": []}

        self.assertIsNone(KoboServices.sync_grievance(None, None))


class RunKoboETLMutationFailureTest(TestCase):
    """A failed sync makes async_mutate return errors, so core marks the MutationLog as failed."""

    @patch("kobo_etl.services.KoboServices.sync_grievance")
    def test_failed_grievance_sync_returns_error(self, sync_grievance):
        sync_grievance.side_effect = KoboServices.KoboSyncError("Grievance sync failed: v2: KoBo down")

        result = RunKoboETLMutation.async_mutate(
            _mock_user(), scope="grievance", start_date=None, end_date=None,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["detail"], "grievance: Grievance sync failed: v2: KoBo down")

    @patch("kobo_etl.services.KoboServices.sync_monetary_transfer")
    @patch("kobo_etl.services.KoboServices.sync_micro_project")
    @patch("kobo_etl.services.KoboServices.sync_bcpromotion")
    @patch("kobo_etl.services.KoboServices.sync_training")
    @patch("kobo_etl.services.KoboServices.sync_grievance")
    def test_scope_all_runs_every_sync_and_reports_the_failed_one(
        self, sync_grievance, sync_training, sync_bcpromotion,
        sync_micro_project, sync_monetary_transfer,
    ):
        sync_training.side_effect = KoboFetchError("KoBo down")

        result = RunKoboETLMutation.async_mutate(
            _mock_user(), scope="all", start_date=None, end_date=None,
        )

        for sync in (sync_grievance, sync_training, sync_bcpromotion,
                     sync_micro_project, sync_monetary_transfer):
            sync.assert_called_once_with(None, None)
        self.assertEqual([e["detail"] for e in result], ["training: KoBo down"])

    @patch("kobo_etl.services.KoboServices.get")
    def test_kobo_unreachable_fails_the_mutation_end_to_end(self, kobo_get):
        kobo_get.side_effect = KoboFetchError("KoBo down")

        result = RunKoboETLMutation.async_mutate(
            _mock_user(), scope="grievance", start_date=None, end_date=None,
        )

        self.assertEqual(len(result), 1)
        self.assertIn("v1: KoBo down", result[0]["detail"])
        self.assertIn("v2: KoBo down", result[0]["detail"])

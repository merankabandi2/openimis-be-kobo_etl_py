from unittest.mock import Mock, patch

import requests
from django.test import TestCase
from graphene import Schema
from graphene.test import Client

from core.models.openimis_graphql_test_case import BaseTestContext
from core.test_helpers import create_test_interactive_user
from kobo_etl.gql_queries import KoboETLStatusType
from kobo_etl.schema import Query
from kobo_etl.services.KoboServices import SCOPE_FORMS
from kobo_etl.strategy import kobo_client

V2_FORM = "atpoVbHXZCdLD9ETHTv6z4"
ETL_FORMS = [uid for uids in SCOPE_FORMS.values() for uid in uids]


def _response(status_code):
    response = Mock()
    response.status_code = status_code
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"{status_code} error", response=response,
        )
    else:
        response.raise_for_status.return_value = None
    return response


def _no_overrides():
    """Environment without any KOBO_TOKEN_<uid> / KOBO_URL_<uid> override."""
    import os
    return {k: v for k, v in os.environ.items() if not k.startswith(("KOBO_TOKEN_", "KOBO_URL_"))}


class KoboStatusIsConfiguredTest(TestCase):
    """isConfigured is true only when every form the ETL syncs resolves a token."""

    def test_false_without_any_token(self):
        with patch.object(kobo_client, "TOKEN", ""), patch.dict("os.environ", _no_overrides(), clear=True):
            self.assertFalse(KoboETLStatusType().resolve_is_configured(None))

    def test_true_with_global_token(self):
        with patch.object(kobo_client, "TOKEN", "global-token"), \
                patch.dict("os.environ", _no_overrides(), clear=True):
            self.assertTrue(KoboETLStatusType().resolve_is_configured(None))

    def test_false_when_a_form_override_is_empty(self):
        env = {**_no_overrides(), f"KOBO_TOKEN_{V2_FORM}": ""}
        with patch.object(kobo_client, "TOKEN", "global-token"), patch.dict("os.environ", env, clear=True):
            self.assertFalse(KoboETLStatusType().resolve_is_configured(None))

    def test_true_when_every_form_has_an_override(self):
        env = {**_no_overrides(), **{f"KOBO_TOKEN_{uid}": "form-token" for uid in ETL_FORMS}}
        with patch.object(kobo_client, "TOKEN", ""), patch.dict("os.environ", env, clear=True):
            self.assertTrue(KoboETLStatusType().resolve_is_configured(None))


@patch("kobo_etl.strategy.kobo_client.requests.get")
class KoboStatusIsReachableTest(TestCase):
    """isReachable is true only when KoBo answers an authenticated request for the ETL forms."""

    def setUp(self):
        for patcher in (patch.object(kobo_client, "TOKEN", "global-token"),
                        patch.dict("os.environ", _no_overrides(), clear=True)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_false_when_kobo_refuses_the_connection(self, requests_get):
        requests_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        self.assertFalse(KoboETLStatusType().resolve_is_reachable(None))

    def test_false_when_kobo_times_out(self, requests_get):
        requests_get.side_effect = requests.exceptions.ConnectTimeout("timed out")

        self.assertFalse(KoboETLStatusType().resolve_is_reachable(None))

    def test_false_when_kobo_rejects_the_token(self, requests_get):
        requests_get.return_value = _response(401)

        self.assertFalse(KoboETLStatusType().resolve_is_reachable(None))

    def test_true_when_kobo_answers(self, requests_get):
        requests_get.return_value = _response(200)

        self.assertTrue(KoboETLStatusType().resolve_is_reachable(None))

    def test_probe_is_authenticated_bounded_and_one_submission(self, requests_get):
        requests_get.return_value = _response(200)

        KoboETLStatusType().resolve_is_reachable(None)

        kwargs = requests_get.call_args.kwargs
        self.assertEqual(kwargs["headers"], {"Authorization": "Token global-token"})
        self.assertEqual(kwargs["params"]["limit"], 1)
        self.assertIsNotNone(kwargs.get("timeout"))
        self.assertIn("/api/v2/assets/", kwargs["url"])

    def test_one_probe_per_server_and_token(self, requests_get):
        requests_get.return_value = _response(200)
        env = {**_no_overrides(),
               f"KOBO_TOKEN_{V2_FORM}": "eu-token",
               f"KOBO_URL_{V2_FORM}": "https://eu.kobo.test"}

        with patch.dict("os.environ", env, clear=True):
            self.assertTrue(KoboETLStatusType().resolve_is_reachable(None))

        urls = [c.kwargs["url"] for c in requests_get.call_args_list]
        self.assertEqual(len(urls), 2)
        self.assertEqual(sum(url.startswith("https://eu.kobo.test/") for url in urls), 1)

    def test_false_when_one_server_is_unreachable(self, requests_get):
        env = {**_no_overrides(),
               f"KOBO_TOKEN_{V2_FORM}": "eu-token",
               f"KOBO_URL_{V2_FORM}": "https://eu.kobo.test"}

        def answer(url, **kwargs):
            if url.startswith("https://eu.kobo.test/"):
                raise requests.exceptions.ConnectionError("Connection refused")
            return _response(200)

        requests_get.side_effect = answer
        with patch.dict("os.environ", env, clear=True):
            self.assertFalse(KoboETLStatusType().resolve_is_reachable(None))

    def test_no_request_without_token(self, requests_get):
        with patch.object(kobo_client, "TOKEN", ""):
            self.assertFalse(KoboETLStatusType().resolve_is_reachable(None))

        requests_get.assert_not_called()


class KoboStatusQueryTest(TestCase):
    """The admin page reads both flags from the koboEtlStatus query."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = create_test_interactive_user(username="kobo_etl_status_admin")

    @patch("kobo_etl.strategy.kobo_client.requests.get",
           side_effect=requests.exceptions.ConnectionError("Connection refused"))
    def test_unreachable_kobo_with_token(self, _requests_get):
        with patch.object(kobo_client, "TOKEN", "global-token"), \
                patch.dict("os.environ", _no_overrides(), clear=True):
            result = Client(Schema(query=Query)).execute(
                "{ koboEtlStatus { isConfigured isReachable } }",
                context=BaseTestContext(self.admin).get_request(),
            )

        self.assertNotIn("errors", result)
        self.assertEqual(result["data"]["koboEtlStatus"], {"isConfigured": True, "isReachable": False})

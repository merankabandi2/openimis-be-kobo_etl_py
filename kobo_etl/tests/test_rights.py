from unittest.mock import patch

from django.test import TestCase
from graphene import Schema
from graphene.test import Client

from core.models import MutationLog
from core.models.openimis_graphql_test_case import BaseTestContext
from core.test_helpers import create_test_interactive_user, create_test_role
from core.utils import collect_all_gql_permissions
from kobo_etl.apps import KoboConfig
from kobo_etl.schema import Mutation, Query

STATUS_QUERY = "{ koboEtlStatus { availableScopes } }"
RUN_MUTATION = """
mutation {
  runKoboEtl(input: {clientMutationId: "%s", scope: GRIEVANCE}) { clientMutationId }
}
"""


class KoboEtlRightCodesTest(TestCase):
    def test_rights_are_declared_in_module_config(self):
        kobo_perms = collect_all_gql_permissions().get("kobo_etl", {})

        self.assertEqual(kobo_perms.get("gql_query_kobo_etl_status_perms"), KoboConfig.gql_query_kobo_etl_status_perms)
        self.assertEqual(kobo_perms.get("gql_mutation_run_kobo_etl_perms"), KoboConfig.gql_mutation_run_kobo_etl_perms)

    def test_rights_are_not_shared_with_another_module(self):
        kobo_codes = set(KoboConfig.gql_query_kobo_etl_status_perms + KoboConfig.gql_mutation_run_kobo_etl_perms)
        for app, app_perms in collect_all_gql_permissions().items():
            if app == "kobo_etl":
                continue
            for perm_name, codes in app_perms.items():
                self.assertFalse(
                    kobo_codes & {str(code) for code in codes},
                    f"{app}.{perm_name} reuses a kobo_etl right code",
                )


@patch("core.async_mutations", False)
@patch("kobo_etl.services.KoboServices.get", return_value={"count": 0, "results": []})
class KoboEtlRightsGraphQLTest(TestCase):
    """Non-admin users are allowed or refused according to RoleRight codes."""

    @classmethod
    def setUpTestData(cls):
        cls.viewer = create_test_interactive_user(
            username="kobo_etl_viewer",
            roles=[create_test_role(["gql_query_kobo_etl_status_perms"], name="KoboEtlViewerRole").id],
        )
        cls.runner = create_test_interactive_user(
            username="kobo_etl_runner",
            roles=[create_test_role(["gql_mutation_run_kobo_etl_perms"], name="KoboEtlRunnerRole").id],
        )
        cls.group_user = create_test_interactive_user(
            username="kobo_etl_group_user",
            roles=[create_test_role(
                ["gql_group_search_perms", "gql_group_create_perms"], name="KoboEtlGroupRole",
            ).id],
        )

    def setUp(self):
        self.client = Client(Schema(query=Query, mutation=Mutation))

    def _execute(self, user, payload):
        return self.client.execute(payload, context=BaseTestContext(user).get_request())

    def _run(self, user, client_mutation_id):
        self._execute(user, RUN_MUTATION % client_mutation_id)
        return MutationLog.objects.get(client_mutation_id=client_mutation_id)

    def test_status_right_allows_status_query(self, _kobo_get):
        result = self._execute(self.viewer, STATUS_QUERY)

        self.assertNotIn("errors", result)
        self.assertIn("grievance", result["data"]["koboEtlStatus"]["availableScopes"])

    def test_run_right_allows_run(self, _kobo_get):
        log = self._run(self.runner, "kobo-etl-runner")

        self.assertEqual(log.status, MutationLog.SUCCESS, log.error)

    def test_status_right_does_not_allow_run(self, _kobo_get):
        log = self._run(self.viewer, "kobo-etl-viewer")

        self.assertEqual(log.status, MutationLog.ERROR)
        self.assertIn("unauthorized", log.error.lower())

    def test_group_rights_do_not_grant_kobo_etl(self, _kobo_get):
        status = self._execute(self.group_user, STATUS_QUERY)
        log = self._run(self.group_user, "kobo-etl-group-user")

        self.assertIn("unauthorized", status["errors"][0]["message"].lower())
        self.assertEqual(log.status, MutationLog.ERROR)
        self.assertIn("unauthorized", log.error.lower())

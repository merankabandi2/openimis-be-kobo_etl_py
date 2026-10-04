"""The KoBo monetary-transfer form is retired: monetary transfers are entered
only on the MIS « Transferts Monétaires » screen, and no KoBo scope pulls them."""
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import CommandError, call_command
from django.test import RequestFactory, TestCase

from core.test_helpers import create_test_interactive_user
from kobo_etl.gql_queries import KoboETLStatusType
from kobo_etl.schema import RunKoboETLMutation
from kobo_etl.services import KoboServices

RUN_KOBO_ETL = ('mutation ($input: RunKoboETLMutationInput!) '
                '{ runKoboEtl(input: $input) { clientMutationId } }')
SCOPES = ('grievance', 'training', 'promotion', 'micro_project')


class MonetaryTransferScopeRetiredTest(TestCase):

    def test_no_sync_scope_pulls_monetary_transfers(self):
        self.assertEqual(tuple(KoboServices.SCOPE_SYNCS), SCOPES)
        self.assertEqual(KoboServices.ALL_SCOPES, SCOPES)
        self.assertEqual(tuple(KoboServices.SCOPE_FORMS), SCOPES)
        self.assertNotIn('monetary_transfer', KoboServices.DRY_RUN_SCOPES)
        for name in ('sync_monetary_transfer', 'MONETARY_TRANSFER_FORM', 'MonetaryTransferConverter',
                     'MODEL_LOCALLY_OWNED_FIELDS', 'sync_rsu_partial', 'sync_rsu_all'):
            self.assertFalse(hasattr(KoboServices, name), name)

    def test_the_command_refuses_the_scope(self):
        with self.assertRaises(CommandError) as ctx:
            call_command('pullkobodata', 'monetary_transfer', stdout=StringIO(), stderr=StringIO())
        self.assertIn("invalid choice: 'monetary_transfer'", str(ctx.exception))

    def test_the_status_lists_no_monetary_transfer_scope(self):
        self.assertEqual(KoboETLStatusType().resolve_available_scopes(None), ['all', *SCOPES])


class RunKoboETLScopeTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_interactive_user(username='kobo_mt_retired')

    def _run(self, scope):
        from openIMIS.schema import schema
        request = RequestFactory().post('/api/graphql')
        request.user = self.user
        with patch.object(RunKoboETLMutation, 'async_mutate', return_value=None) as mutate:
            result = schema.execute(RUN_KOBO_ETL, context_value=request,
                                    variable_values={'input': {'scope': scope, 'clientMutationId': 'mt'}})
        return [str(e) for e in (result.errors or [])], mutate

    def test_the_mutation_accepts_a_kobo_scope(self):
        errors, mutate = self._run('MICRO_PROJECT')
        self.assertEqual(errors, [])
        self.assertEqual(mutate.call_args.kwargs['scope'], 'micro_project')

    def test_the_mutation_refuses_monetary_transfer(self):
        errors, mutate = self._run('MONETARY_TRANSFER')
        self.assertEqual(len(errors), 1)
        self.assertIn('Expected type "KoboETLScopeEnum", found "MONETARY_TRANSFER"', errors[0])
        mutate.assert_not_called()

    def test_the_mutation_scope_all_runs_every_kobo_scope(self):
        user = Mock(id=1, username='test-user')
        user.has_perms.return_value = True
        syncs = {scope: Mock(return_value=KoboServices.SyncResult()) for scope in SCOPES}

        with patch.multiple(KoboServices, sync_grievance=syncs['grievance'],
                            sync_training=syncs['training'], sync_bcpromotion=syncs['promotion'],
                            sync_micro_project=syncs['micro_project']):
            result = RunKoboETLMutation.async_mutate(user, scope='all', start_date=None, end_date=None)

        self.assertIsNone(result)
        for sync in syncs.values():
            sync.assert_called_once_with(None, None)

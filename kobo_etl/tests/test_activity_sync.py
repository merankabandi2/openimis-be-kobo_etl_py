"""KoBo activity syncs (training, promotion, micro_project) through pullkobodata and the Celery task."""
import datetime
import json
import uuid
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from location.test_helpers import create_test_location
from merankabandi.models import MicroProject, OtherProjectType, SensitizationTraining
from kobo_etl.services import KoboServices
from kobo_etl.strategy import kobo_client
from kobo_etl.strategy.kobo_client import KoboFetchError
from kobo_etl.tasks import NIGHTLY_SCOPES, pull_kobo_data

# KoBo colline codes carry a zone digit (5th) that the MIS location code drops.
KOBO_COLLINE = '9906107'
IMIS_COLLINE = '990607'
UNKNOWN_KOBO_COLLINE = '9807301'


def _create_colline():
    province = create_test_location('D', custom_props={'code': '99', 'name': 'Province99'})
    commune = create_test_location('W', custom_props={'code': '9906', 'name': 'Commune9906',
                                                      'parent': province})
    return create_test_location('V', custom_props={'code': IMIS_COLLINE, 'name': 'Colline990607',
                                                   'parent': commune})


def _micro_project(uid=None, colline=KOBO_COLLINE, others=None, homme='3'):
    return {
        '_uuid': uid or str(uuid.uuid4()),
        '_id': 1,
        'Date': '2026-08-18',
        'group_ln06g44/Colline': colline,
        'group_bh77o90/Homme': homme,
        'group_bh77o90/Femme': '5',
        'group_bh77o90/Twa': '0',
        'group_fb09e52/Agriculture': '4',
        'group_fb09e52/group_mu7lt44': others if others is not None else [
            {'Autre_pr_ciser': 'Couture', 'Effectif': '2'},
        ],
    }


def _training(uid=None, men='7'):
    return {
        '_uuid': uid or str(uuid.uuid4()),
        '_id': 2,
        'Date_de_la_sensibilisation_Formation': '2026-08-18',
        'group_ln06g44/Colline': KOBO_COLLINE,
        'group_zp4mt03/Nombre_dhommes': men,
        'group_zp4mt03/Nombre_de_femmes': '9',
        'group_zp4mt03/Nombre_de_Batwa': '1',
        'Th_me': 'module_mip__mesures_d_inclusio',
    }


def _kobo(results):
    return {'count': len(results), 'results': results}


def _pull(*args):
    out = StringIO()
    call_command('pullkobodata', *args, stdout=out, stderr=StringIO())
    return out.getvalue()


class MicroProjectSyncTest(TestCase):

    def setUp(self):
        _create_colline()

    @patch('kobo_etl.services.KoboServices.get')
    def test_resync_updates_the_imported_micro_project(self, kobo_get):
        data = _micro_project()
        kobo_get.return_value = _kobo([data])
        _pull('micro_project')

        kobo_get.return_value = _kobo([{**data, 'group_bh77o90/Homme': '6'}, _micro_project()])
        output = _pull('micro_project')

        self.assertEqual(MicroProject.objects.count(), 2)
        self.assertEqual(MicroProject.objects.get(id=data['_uuid']).male_participants, 6)
        self.assertIn('micro_project: 2 submissions fetched, 1 created, 1 updated, 0 skipped', output)

    @patch('kobo_etl.services.KoboServices.get')
    def test_other_project_types_are_replaced_not_duplicated(self, kobo_get):
        data = _micro_project()
        kobo_get.return_value = _kobo([data])

        _pull('micro_project')
        _pull('micro_project')

        self.assertEqual(
            list(OtherProjectType.objects.values_list('name', 'beneficiary_count')), [('Couture', 2)],
        )

    @patch('kobo_etl.services.KoboServices.get')
    def test_submission_without_mis_location_is_skipped(self, kobo_get):
        kobo_get.return_value = _kobo([_micro_project(), _micro_project(colline=UNKNOWN_KOBO_COLLINE)])

        with self.assertLogs('kobo_etl.services.KoboServices', level='WARNING') as logs:
            output = _pull('micro_project')

        self.assertEqual(MicroProject.objects.count(), 1)
        self.assertIn('1 created, 0 updated, 1 skipped', output)
        self.assertIn('micro_project: 1 of 2 KoBo submissions skipped', '\n'.join(logs.output))

    @patch('kobo_etl.services.KoboServices.get')
    def test_dry_run_writes_nothing_and_classifies(self, kobo_get):
        existing = _micro_project()
        kobo_get.return_value = _kobo([existing])
        _pull('micro_project')

        kobo_get.return_value = _kobo([
            {**existing, 'group_bh77o90/Homme': '6'}, _micro_project(),
            _micro_project(colline=UNKNOWN_KOBO_COLLINE),
        ])
        output = _pull('micro_project', '--dry-run')

        self.assertEqual(MicroProject.objects.count(), 1)
        self.assertEqual(MicroProject.objects.get(id=existing['_uuid']).male_participants, 3)
        self.assertEqual(OtherProjectType.objects.count(), 1)
        self.assertIn(
            'micro_project: 3 submissions fetched, 1 would be created, 1 would be updated, 1 skipped', output,
        )


class ValidationSurvivesResyncTest(TestCase):

    def setUp(self):
        _create_colline()

    @patch('kobo_etl.services.KoboServices.get')
    def test_validated_training_keeps_its_validation(self, kobo_get):
        data = _training()
        kobo_get.return_value = _kobo([data])
        _pull('training')
        validated_at = datetime.datetime(2026, 9, 1, 10, 0)
        SensitizationTraining.objects.filter(id=data['_uuid']).update(
            validation_status='VALIDATED', validation_date=validated_at, validation_comment='ok',
        )

        kobo_get.return_value = _kobo([{**data, 'group_zp4mt03/Nombre_dhommes': '8'}])
        _pull('training')

        training = SensitizationTraining.objects.get(id=data['_uuid'])
        self.assertEqual(training.male_participants, 8)
        self.assertEqual(
            (training.validation_status, training.validation_date, training.validation_comment),
            ('VALIDATED', validated_at, 'ok'),
        )


class PullKoboDataCommandTest(TestCase):

    @patch('kobo_etl.services.KoboServices.get')
    def test_date_range_is_passed_to_kobo(self, kobo_get):
        kobo_get.return_value = _kobo([])

        _pull('training', '--from', '2026-09-01', '--to', '2026-09-28')

        kobo_get.assert_called_once_with(
            KoboServices.TRAINING_FORM,
            start_date=datetime.date(2026, 9, 1), end_date=datetime.date(2026, 9, 28),
        )

    def test_invalid_range_is_refused(self):
        with self.assertRaises(CommandError):
            _pull('training', '--from', '2026-09-28', '--to', '2026-09-01')
        with self.assertRaises(CommandError):
            _pull('training', '--from', '28/09/2026')

    def test_dry_run_of_grievance_is_refused_before_any_fetch(self):
        with patch('kobo_etl.services.KoboServices.get') as kobo_get:
            with self.assertRaises(CommandError):
                _pull('all', '--dry-run')
        kobo_get.assert_not_called()

    def test_all_runs_every_scope_then_fails(self):
        syncs = {scope: Mock(return_value=KoboServices.SyncResult()) for scope in KoboServices.SCOPE_SYNCS}
        syncs['training'].side_effect = KoboFetchError('KoBo down')

        with patch.dict(KoboServices.SCOPE_SYNCS, syncs):
            with self.assertRaises(CommandError) as ctx:
                _pull('all')

        for sync in syncs.values():
            sync.assert_called_once_with(None, None, dry_run=False)
        self.assertEqual(str(ctx.exception), 'KoBo sync failed for: training')


class PullKoboDataTaskTest(TestCase):

    def test_nightly_scopes_match_the_host_cron(self):
        self.assertEqual(NIGHTLY_SCOPES, ('grievance', 'training', 'promotion', 'micro_project'))

    def test_failed_scope_fails_the_task_after_the_others(self):
        calls = []

        def sync(name, fail=False):
            def run(start_date, end_date, dry_run=False):
                calls.append(name)
                if fail:
                    raise KoboFetchError('KoBo down')
                return KoboServices.SyncResult(fetched=1, created=1)
            return run

        with patch.dict(KoboServices.SCOPE_SYNCS, {
            'grievance': sync('grievance', fail=True), 'training': sync('training'),
            'promotion': sync('promotion'), 'micro_project': sync('micro_project'),
        }):
            with self.assertRaises(KoboServices.KoboSyncError) as ctx:
                pull_kobo_data()

        self.assertEqual(calls, list(NIGHTLY_SCOPES))
        self.assertEqual(str(ctx.exception), 'KoBo pull failed for: grievance')


class KoboClientDateRangeTest(TestCase):

    @patch('kobo_etl.strategy.kobo_client.requests.get')
    def test_query_selects_the_submission_days(self, requests_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {'count': 0, 'next': None, 'results': []}
        requests_get.return_value = response

        kobo_client.get('form', start_date=datetime.date(2026, 9, 1), end_date=datetime.date(2026, 9, 28))

        query = json.loads(requests_get.call_args.kwargs['params']['query'])
        self.assertEqual(query, {'_submission_time': {
            '$gte': '2026-09-01T00:00:00', '$lt': '2026-09-29T00:00:00',
        }})

    @patch('kobo_etl.strategy.kobo_client.requests.get')
    def test_no_range_sends_no_query(self, requests_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {'count': 0, 'next': None, 'results': []}
        requests_get.return_value = response

        kobo_client.get('form')

        self.assertNotIn('query', requests_get.call_args.kwargs['params'])

"""KoBo activity syncs (training, micro_project) through pullkobodata."""
import datetime
import uuid
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from location.test_helpers import create_test_location
from merankabandi.models import MicroProject, OtherProjectType, SensitizationTraining
from kobo_etl.services import KoboServices

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


def _micro_project(uid=None, colline=KOBO_COLLINE, homme='3'):
    return {
        '_uuid': uid or str(uuid.uuid4()),
        '_id': 1,
        'Date': '2026-08-18',
        'group_ln06g44/Colline': colline,
        'group_bh77o90/Homme': homme,
        'group_bh77o90/Femme': '5',
        'group_bh77o90/Twa': '0',
        'group_fb09e52/Agriculture': '4',
        'group_fb09e52/group_mu7lt44': [{'Autre_pr_ciser': 'Couture', 'Effectif': '2'}],
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

    def test_dry_run_of_grievance_is_refused_before_any_fetch(self):
        with patch('kobo_etl.services.KoboServices.get') as kobo_get:
            with self.assertRaises(CommandError):
                _pull('all', '--dry-run')
        kobo_get.assert_not_called()

    def test_all_runs_every_scope_then_fails(self):
        syncs = {scope: Mock(return_value=KoboServices.SyncResult()) for scope in KoboServices.SCOPE_SYNCS}
        syncs['training'].side_effect = RuntimeError('KoBo down')

        with patch.dict(KoboServices.SCOPE_SYNCS, syncs):
            with self.assertRaises(CommandError) as ctx:
                _pull('all')

        for sync in syncs.values():
            sync.assert_called_once_with(None, None, dry_run=False)
        self.assertEqual(str(ctx.exception), 'KoBo sync failed for: training')

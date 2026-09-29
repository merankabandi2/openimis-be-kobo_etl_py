"""sync_micro_project re-imports micro-projects already in the MIS without IntegrityError."""
import uuid
from unittest.mock import patch

from django.test import TestCase

from location.test_helpers import create_test_location
from merankabandi.models import MicroProject, OtherProjectType
from kobo_etl.services import KoboServices

# KoBo colline codes carry a zone digit (5th) that the MIS location code drops.
KOBO_COLLINE = '9906107'
IMIS_COLLINE = '990607'


def _submission(uid=None, homme='3'):
    return {
        '_uuid': uid or str(uuid.uuid4()),
        '_id': 1,
        'Date': '2026-08-18',
        'group_ln06g44/Colline': KOBO_COLLINE,
        'group_bh77o90/Homme': homme,
        'group_bh77o90/Femme': '5',
        'group_bh77o90/Twa': '0',
        'group_fb09e52/group_mu7lt44': [{'Autre_pr_ciser': 'Couture', 'Effectif': '2'}],
    }


class SyncMicroProjectTest(TestCase):

    def setUp(self):
        province = create_test_location('D', custom_props={'code': '99', 'name': 'Province99'})
        commune = create_test_location('W', custom_props={'code': '9906', 'name': 'Commune9906',
                                                          'parent': province})
        create_test_location('V', custom_props={'code': IMIS_COLLINE, 'name': 'Colline990607',
                                                'parent': commune})

    @patch('kobo_etl.services.KoboServices.get')
    def test_resync_imports_new_and_updates_existing(self, kobo_get):
        existing = _submission()
        kobo_get.return_value = {'count': 1, 'results': [existing]}
        KoboServices.sync_micro_project(None, None)

        kobo_get.return_value = {'count': 2, 'results': [{**existing, 'group_bh77o90/Homme': '6'}, _submission()]}
        KoboServices.sync_micro_project(None, None)

        self.assertEqual(MicroProject.objects.count(), 2)
        self.assertEqual(MicroProject.objects.get(id=existing['_uuid']).male_participants, 6)
        self.assertEqual(OtherProjectType.objects.count(), 2)
        self.assertEqual(OtherProjectType.objects.filter(microproject_id=existing['_uuid']).count(), 1)

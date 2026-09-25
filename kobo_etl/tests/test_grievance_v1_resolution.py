import uuid
from unittest import mock

from django.test import TestCase

from core.test_helpers import create_test_interactive_user
from grievance_social_protection.apps import TicketConfig
from grievance_social_protection.models import Ticket
from kobo_etl.builders.kobo.GrievanceConverter import GrievanceConverter
from kobo_etl.services import KoboServices

V1_FORM = "aeAgbxjy7d6rD8jtUdMD9Z"

RESOLUTION_TIMES = {
    'Default': '5,0',
    'violence_vbg': '2,0',
    'paiement': '4,0',
}


def _v1_submission(**fields):
    data = {
        '_uuid': str(uuid.uuid4()),
        'id_plainte': 'KOBO-V1-TEST',
        'description_plainte': 'test',
        'plainte_resolue': 'non',
    }
    data.update(fields)
    return data


@mock.patch.object(TicketConfig, 'unified_resolution_times', RESOLUTION_TIMES)
class GrievanceV1ConverterResolutionTest(TestCase):
    """A v1 KoBo ticket gets its category's default resolution delay."""

    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_interactive_user(username="kobo_v1_import")

    def setUp(self):
        patcher = mock.patch.dict('os.environ', {'KOBO_IMPORT_USERNAME': self.user.username})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_category_delay(self):
        ticket = GrievanceConverter.to_data_element_obj(
            _v1_submission(**{'group_categorie/categories_sensibles': 'violence_vbg'}))

        self.assertEqual(ticket.category, 'violence_vbg')
        self.assertEqual(ticket.resolution, '2,0')

    def test_sub_category_takes_its_parent_delay(self):
        ticket = GrievanceConverter.to_data_element_obj(
            _v1_submission(**{'group_categorie/categories_non_sensibles': 'paiement_pas_recu'}))

        self.assertEqual(ticket.category, 'paiement')
        self.assertEqual(ticket.resolution, '4,0')

    def test_uncategorized_takes_the_default_delay(self):
        ticket = GrievanceConverter.to_data_element_obj(_v1_submission())

        self.assertEqual(ticket.category, 'uncategorized')
        self.assertEqual(ticket.resolution, '5,0')

    def test_no_configured_delay_leaves_resolution_empty(self):
        with mock.patch.object(TicketConfig, 'unified_resolution_times', {}), \
                mock.patch.object(TicketConfig, 'default_resolution', {}):
            ticket = GrievanceConverter.to_data_element_obj(_v1_submission())

        self.assertIsNone(ticket.resolution)


@mock.patch.object(TicketConfig, 'unified_resolution_times', RESOLUTION_TIMES)
class SyncGrievanceV1ResolutionTest(TestCase):
    """sync_grievance stores the default resolution delay on imported v1 tickets."""

    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_interactive_user(username="kobo_v1_sync")

    def setUp(self):
        patcher = mock.patch.dict('os.environ', {'KOBO_IMPORT_USERNAME': self.user.username})
        patcher.start()
        self.addCleanup(patcher.stop)

    @mock.patch("kobo_etl.services.KoboServices.get")
    def test_imported_v1_ticket_has_resolution(self, kobo_get):
        vbg = _v1_submission(**{'group_categorie/categories_sensibles': 'violence_vbg'})
        other = _v1_submission()
        kobo_get.side_effect = lambda uid: {"count": 2, "results": [vbg, other]} if uid == V1_FORM \
            else {"count": 0, "results": []}

        KoboServices.sync_grievance(None, None)

        tickets = {str(t.id): t for t in Ticket.objects.filter(id__in=[vbg['_uuid'], other['_uuid']])}
        self.assertEqual(len(tickets), 2)
        self.assertEqual(tickets[vbg['_uuid']].resolution, '2,0')
        self.assertEqual(tickets[other['_uuid']].resolution, '5,0')

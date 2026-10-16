import uuid
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from core.test_helpers import create_test_interactive_user
from grievance_social_protection.apps import TicketConfig
from grievance_social_protection.models import Ticket
from kobo_etl.builders.kobo.GrievanceConverter import GrievanceConverter
from kobo_etl.services import KoboServices
from merankabandi.tests.grievance_config_helpers import use_grievance_categories

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
        use_grievance_categories(self)

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
        use_grievance_categories(self)

    @mock.patch("kobo_etl.services.KoboServices.get")
    def test_imported_v1_ticket_has_resolution(self, kobo_get):
        vbg = _v1_submission(**{'group_categorie/categories_sensibles': 'violence_vbg'})
        other = _v1_submission()
        kobo_get.side_effect = lambda uid, **kwargs: {"count": 2, "results": [vbg, other]} if uid == V1_FORM \
            else {"count": 0, "results": []}

        KoboServices.sync_grievance(None, None)

        tickets = {str(t.id): t for t in Ticket.objects.filter(id__in=[vbg['_uuid'], other['_uuid']])}
        self.assertEqual(len(tickets), 2)
        self.assertEqual(tickets[vbg['_uuid']].resolution, '2,0')
        self.assertEqual(tickets[other['_uuid']].resolution, '5,0')


class SyncGrievanceV1CountLogTest(TestCase):
    """The v1 sync log line counts the tickets created and the submissions
    skipped because their ticket already exists."""

    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_interactive_user(username="kobo_v1_count")

    def setUp(self):
        patcher = mock.patch.dict('os.environ', {'KOBO_IMPORT_USERNAME': self.user.username})
        patcher.start()
        self.addCleanup(patcher.stop)
        use_grievance_categories(self)

    def _sync_lines(self, submissions):
        with mock.patch("kobo_etl.services.KoboServices.get") as kobo_get, \
                self.assertLogs('kobo_etl.services.KoboServices', level='INFO') as logs:
            kobo_get.side_effect = lambda uid, **kwargs: {"count": len(submissions), "results": submissions} \
                if uid == V1_FORM else {"count": 0, "results": []}
            KoboServices.sync_grievance(None, None)
        return [line for line in logs.output if 'v1' in line]

    def test_first_sync_counts_created_tickets(self):
        lines = self._sync_lines([_v1_submission(), _v1_submission()])
        self.assertEqual(len(lines), 1)
        self.assertIn('Synced v1: 2 created, 0 skipped (existing), 2 submissions', lines[0])

    def test_second_sync_counts_existing_tickets_as_skipped(self):
        known = _v1_submission()
        self._sync_lines([known])

        lines = self._sync_lines([known, _v1_submission()])

        self.assertEqual(len(lines), 1)
        self.assertIn('Synced v1: 1 created, 1 skipped (existing), 2 submissions', lines[0])


class GrievanceV1VbgTest(TestCase):
    """A v1 VBG/EAS/HS ticket keeps no identity (manual MGP FA2 p. 40) and
    starts the VBG/EAS/HS procedure (mis#310, mis#311)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_interactive_user(username="kobo_v1_vbg")
        create_test_interactive_user(username="Admin")
        call_command('seed_workflow_templates', stdout=StringIO())

    def setUp(self):
        patcher = mock.patch.dict('os.environ', {'KOBO_IMPORT_USERNAME': self.user.username})
        patcher.start()
        self.addCleanup(patcher.stop)
        use_grievance_categories(self)

    def _vbg(self, **fields):
        return _v1_submission(**{
            'group_categorie/categories_sensibles': 'violence_vbg',
            'est_anonyme': 'non', 'nom_plaignant': 'Nom', 'tel_plaignant': '79000000',
            'numero_cni': '1/2', 'genre_plaignant': 'F', 'group_im0ri26/Localisation': '-3 29 0 0',
            **fields,
        })

    def test_vbg_ticket_keeps_no_identity(self):
        ticket = GrievanceConverter.to_data_element_obj(self._vbg())
        self.assertNotIn('name', ticket.json_ext['reporter'])
        self.assertNotIn('phone', ticket.json_ext['reporter'])
        self.assertNotIn('cni_number', ticket.json_ext['reporter'])
        self.assertNotIn('gps', ticket.json_ext['location'])
        self.assertEqual(ticket.json_ext['reporter']['gender'], 'F')

    def test_other_ticket_keeps_its_reporter(self):
        ticket = GrievanceConverter.to_data_element_obj(_v1_submission(**{
            'group_categorie/categories_non_sensibles': 'paiement', 'nom_plaignant': 'Nom'}))
        self.assertEqual(ticket.json_ext['reporter']['name'], 'Nom')

    @mock.patch("kobo_etl.services.KoboServices.get")
    def test_sync_starts_the_vbg_procedure_on_new_open_tickets_only(self, kobo_get):
        open_vbg = self._vbg()
        resolved_vbg = self._vbg(plainte_resolue='oui')
        other = _v1_submission()
        kobo_get.side_effect = lambda uid, **kwargs: {
            "count": 3, "results": [open_vbg, resolved_vbg, other]} if uid == V1_FORM \
            else {"count": 0, "results": []}

        KoboServices.sync_grievance(None, None)

        tickets = {str(t.id): t for t in Ticket.objects.filter(
            id__in=[open_vbg['_uuid'], resolved_vbg['_uuid'], other['_uuid']])}
        self.assertEqual(list(tickets[open_vbg['_uuid']].workflows.values_list(
            'template__name', flat=True)), ['vbg_eas_hs_fa2'])
        self.assertFalse(tickets[resolved_vbg['_uuid']].workflows.exists())
        self.assertFalse(tickets[other['_uuid']].workflows.exists())
        self.assertNotIn('name', tickets[open_vbg['_uuid']].json_ext['reporter'])


class GrievanceV1WorkflowTest(TestCase):
    """New open v1 tickets of every category get their workflow, as v2 tickets
    do (mis#324); tickets imported before get none from a later sync."""

    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_interactive_user(username="kobo_v1_workflow")
        create_test_interactive_user(username="Admin")
        call_command('seed_workflow_templates', stdout=StringIO())

    def setUp(self):
        patcher = mock.patch.dict('os.environ', {'KOBO_IMPORT_USERNAME': self.user.username})
        patcher.start()
        self.addCleanup(patcher.stop)
        use_grievance_categories(self)

    def _sync(self, kobo_get, submissions):
        kobo_get.side_effect = lambda uid, **kwargs: {
            "count": len(submissions), "results": submissions} if uid == V1_FORM \
            else {"count": 0, "results": []}
        KoboServices.sync_grievance(None, None)

    def _templates(self, submission):
        return list(Ticket.objects.get(id=submission['_uuid']).workflows.values_list('template__name', flat=True))

    @mock.patch("kobo_etl.services.KoboServices.get")
    def test_new_open_payment_ticket_gets_its_workflow(self, kobo_get):
        payment = _v1_submission(**{'group_categorie/categories_non_sensibles': 'paiement_pas_recu'})
        resolved = _v1_submission(**{'group_categorie/categories_non_sensibles': 'paiement_pas_recu',
                                     'plainte_resolue': 'oui'})
        self._sync(kobo_get, [payment, resolved])

        self.assertEqual(self._templates(payment), ['payment_non_reception'])
        self.assertEqual(self._templates(resolved), [])

    @mock.patch("kobo_etl.services.KoboServices.get")
    def test_ticket_imported_before_gets_no_workflow_from_a_later_sync(self, kobo_get):
        payment = _v1_submission(**{'group_categorie/categories_non_sensibles': 'paiement_pas_recu'})
        ticket = GrievanceConverter.to_data_element_obj(payment)
        KoboServices.bulk_upsert(model_class=Ticket, data_list=[ticket], update_fields=[])

        self._sync(kobo_get, [payment])

        self.assertEqual(self._templates(payment), [])

    @mock.patch("kobo_etl.services.KoboServices.get")
    def test_uncategorized_ticket_gets_no_workflow(self, kobo_get):
        uncategorized = _v1_submission()
        self._sync(kobo_get, [uncategorized])

        self.assertEqual(Ticket.objects.get(id=uncategorized['_uuid']).category, 'uncategorized')
        self.assertEqual(self._templates(uncategorized), [])

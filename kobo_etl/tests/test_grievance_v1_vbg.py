"""v1 KoBo VBG/EAS/HS tickets keep no identity (manual MGP FA2 p. 40) and
start the VBG/EAS/HS procedure (mis#310, mis#311)."""
import uuid
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from core.test_helpers import create_test_interactive_user
from grievance_social_protection.models import Ticket
from kobo_etl.builders.kobo.GrievanceConverter import GrievanceConverter
from kobo_etl.services import KoboServices

V1_FORM = "aeAgbxjy7d6rD8jtUdMD9Z"


def _v1_submission(**fields):
    data = {
        '_uuid': str(uuid.uuid4()),
        'id_plainte': 'KOBO-V1-TEST',
        'description_plainte': 'test',
        'plainte_resolue': 'non',
    }
    data.update(fields)
    return data


class GrievanceV1VbgTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_interactive_user(username="kobo_v1_vbg")
        create_test_interactive_user(username="Admin")
        call_command('seed_workflow_templates', stdout=StringIO())

    def setUp(self):
        patcher = mock.patch.dict('os.environ', {'KOBO_IMPORT_USERNAME': self.user.username})
        patcher.start()
        self.addCleanup(patcher.stop)

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

"""v1 KoBo grievances: a numeric colline value is a KoBo colline code, resolved
through KoboLocationCrosswalk. A colline name is resolved within the KoBo zone of
the submission (group_im0ri26/zone): the crosswalk row of that zone carrying the
label, else a valid MIS colline of that name in the commune the crosswalk maps
the zone's commune to. A name is never matched across the country (mis#262)."""
import datetime
import uuid
from unittest import mock

from django.test import TestCase

from core.test_helpers import create_test_interactive_user
from kobo_etl.builders.kobo.GrievanceConverter import GrievanceConverter, _resolve_colline
from location.models import Location
from location.test_helpers import create_test_location
from merankabandi.models import KoboLocationCrosswalk


def _located(colline):
    return {'colline_code': colline.code, 'location_id': str(colline.id)}


class GrievanceV1CollineResolutionTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        tag = uuid.uuid4().hex[:4]
        makamba = create_test_location('D', custom_props={'code': f'P1{tag}', 'name': 'Makamba'})
        muramvya = create_test_location('D', custom_props={'code': f'P2{tag}', 'name': 'Muramvya'})
        cls.kayogoro = create_test_location('W', custom_props={'code': f'C1{tag}', 'name': 'Kayogoro',
                                                               'parent': makamba})
        cls.bukeye = create_test_location('W', custom_props={'code': f'C2{tag}', 'name': 'Bukeye',
                                                             'parent': muramvya})

        def colline(code, name, commune):
            return create_test_location('V', custom_props={'code': f'{code}{tag}', 'name': name,
                                                           'parent': commune})

        # The same colline names in two communes.
        cls.bigina_kayogoro = colline('V1', 'Bigina', cls.kayogoro)
        cls.bigina_bukeye = colline('V2', 'Bigina', cls.bukeye)
        cls.kigoma_kayogoro = colline('V3', 'Kigoma', cls.kayogoro)
        cls.kigoma_bukeye = colline('V4', 'Kigoma', cls.bukeye)
        cls.buhorwa = colline('V5', 'Buhorwa', cls.bukeye)

        # KoBo colline code = KoBo commune code + zone digit + two digits.
        for code, label, location in (
                ('1001101', 'BIGINA', cls.bigina_kayogoro),
                ('1001102', 'Gatabo', None),
                ('1101101', 'Bigina', cls.bigina_bukeye),
                ('1101102', 'Buhorwa', cls.buhorwa)):
            KoboLocationCrosswalk.objects.create(
                kobo_code=code, kobo_colline_label=label, location=location,
                match_method=KoboLocationCrosswalk.MATCH_EXACT if location else KoboLocationCrosswalk.MATCH_UNMATCHED)

    def test_kobo_code_goes_to_its_crosswalk_colline(self):
        self.assertEqual(_resolve_colline('1101102'), _located(self.buhorwa))

    def test_kobo_code_without_crosswalk_row_is_not_cut_into_a_mis_code(self):
        self.assertEqual(_resolve_colline('1101109'), {})

    def test_name_goes_to_the_crosswalk_colline_of_its_zone(self):
        self.assertEqual(_resolve_colline('bigina', '11011'), _located(self.bigina_bukeye))
        self.assertEqual(_resolve_colline('Bigina ', '10011'), _located(self.bigina_kayogoro))

    def test_name_outside_the_crosswalk_is_looked_up_in_the_commune_of_its_zone(self):
        self.assertEqual(_resolve_colline('Kigoma', '10011'), _located(self.kigoma_kayogoro))
        self.assertEqual(_resolve_colline('Kigoma', '11012'), _located(self.kigoma_bukeye))

    def test_name_without_zone_is_not_matched_across_the_country(self):
        # Replaces the former nationwide name match, which took the first colline of that name.
        self.assertEqual(_resolve_colline('Bigina'), {})
        self.assertEqual(_resolve_colline('Buhorwa'), {})

    def test_name_absent_from_the_commune_of_its_zone_is_not_resolved(self):
        self.assertEqual(_resolve_colline('Buhorwa', '10011'), {})

    def test_closed_colline_is_never_returned(self):
        Location.objects.filter(id=self.kigoma_kayogoro.id).update(validity_to=datetime.datetime(2025, 3, 1))
        self.assertEqual(_resolve_colline('Kigoma', '10011'), {})
        self.assertEqual(_resolve_colline(self.kigoma_kayogoro.code), {})


class GrievanceV1LocationJsonTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_interactive_user(username=f'kobo_v1_loc_{uuid.uuid4().hex[:4]}')
        province = create_test_location('D', custom_props={'code': 'PL1', 'name': 'P'})
        commune = create_test_location('W', custom_props={'code': 'CL1', 'name': 'C', 'parent': province})
        cls.colline = create_test_location('V', custom_props={'code': 'VL1', 'name': 'Rabiro', 'parent': commune})
        KoboLocationCrosswalk.objects.create(kobo_code='901301', kobo_colline_label='Rabiro', location=cls.colline,
                                             match_method=KoboLocationCrosswalk.MATCH_EXACT)

    def _ticket(self, **fields):
        data = {'_uuid': str(uuid.uuid4()), 'id_plainte': 'V1', 'description_plainte': 'd',
                'plainte_resolue': 'non', **fields}
        with mock.patch.dict('os.environ', {'KOBO_IMPORT_USERNAME': self.user.username}):
            return GrievanceConverter.to_data_element_obj(data)

    def test_resolved_location_keeps_the_form_values(self):
        ticket = self._ticket(**{'group_im0ri26/zone': '9013', 'group_im0ri26/colline': 'rabiro'})
        self.assertEqual(ticket.json_ext['location'], {
            'colline_code': 'VL1', 'location_id': str(self.colline.id), 'gps': None,
            'kobo_colline_label': 'rabiro', 'kobo_zone': '9013'})

    def test_unresolved_location_keeps_the_form_values(self):
        ticket = self._ticket(**{'group_im0ri26/colline': 'Rabiro'})
        self.assertEqual(ticket.json_ext['location'], {
            'colline_code': '', 'location_id': None, 'gps': None, 'kobo_colline_label': 'Rabiro', 'kobo_zone': ''})

    def test_backfill_does_not_place_an_unresolved_ticket_by_name_across_the_country(self):
        from io import StringIO

        from django.core.management import call_command
        from grievance_social_protection.models import Ticket

        # « Rubira » is the name of one colline, in a commune the zone does not give.
        province = create_test_location('D', custom_props={'code': 'PL2', 'name': 'P2'})
        commune = create_test_location('W', custom_props={'code': 'CL2', 'name': 'C2', 'parent': province})
        create_test_location('V', custom_props={'code': 'VL2', 'name': 'Rubira', 'parent': commune})
        ticket = self._ticket(**{'group_im0ri26/zone': '9013', 'group_im0ri26/colline': 'Rubira'})
        ticket.save(username=self.user.username)

        call_command('backfill_ticket_locations', stdout=StringIO())

        location = Ticket.objects.get(id=ticket.id).json_ext['location']
        self.assertEqual(location['colline_code'], '')
        self.assertIsNone(location['location_id'])

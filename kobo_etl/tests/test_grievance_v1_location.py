"""v1 KoBo grievances: a numeric colline value is a KoBo colline code, resolved
through KoboLocationCrosswalk; a name is matched by name."""
from django.test import TestCase

from kobo_etl.builders.kobo.GrievanceConverter import _resolve_colline
from location.test_helpers import create_test_location
from merankabandi.models import KoboLocationCrosswalk


class GrievanceV1CollineResolutionTest(TestCase):

    def setUp(self):
        makamba = create_test_location('D', custom_props={'code': '10', 'name': 'Makamba'})
        kayogoro = create_test_location('W', custom_props={'code': '1001', 'name': 'Kayogoro',
                                                           'parent': makamba})
        muramvya = create_test_location('D', custom_props={'code': '11', 'name': 'Muramvya'})
        bukeye = create_test_location('W', custom_props={'code': '1101', 'name': 'Bukeye', 'parent': muramvya})
        self.bigina = create_test_location('V', custom_props={'code': '100101', 'name': 'Bigina',
                                                              'parent': kayogoro})
        # 1101101 with its zone digit cut out.
        self.buhorwa = create_test_location('V', custom_props={'code': '110101', 'name': 'Buhorwa',
                                                               'parent': bukeye})

    def test_kobo_code_goes_to_its_crosswalk_colline(self):
        KoboLocationCrosswalk.objects.create(kobo_code='1101101', location=self.bigina,
                                             match_method=KoboLocationCrosswalk.MATCH_EXACT)
        self.assertEqual(_resolve_colline('1101101'),
                         {'colline_code': '100101', 'location_id': str(self.bigina.id)})

    def test_kobo_code_without_crosswalk_row_is_not_cut_into_a_mis_code(self):
        self.assertEqual(_resolve_colline('1101101'), {})

    def test_name_is_still_matched(self):
        self.assertEqual(_resolve_colline('Buhorwa'),
                         {'colline_code': '110101', 'location_id': str(self.buhorwa.id)})

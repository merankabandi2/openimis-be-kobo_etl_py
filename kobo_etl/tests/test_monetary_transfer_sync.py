"""A KoBo monetary-transfer pull never overwrites what the MIS owns, and the
"all" scope does not pull monetary transfers."""
import datetime
import uuid
from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase

from core.test_helpers import create_test_interactive_user
from location.test_helpers import create_test_location
from merankabandi.models import MonetaryTransfer, PaymentAgency
from social_protection.models import BenefitPlan

from kobo_etl.schema import RunKoboETLMutation
from kobo_etl.services import KoboServices

KOBO_COLLINE = '9906107'
IMIS_COLLINE = '990607'
AGENCY = 'Agence KoBo test'


def _submission(uid, paid_women='4'):
    """A submission of form ayK8Y5yP3MPTYQ3cPcpj9N: it has no amount field."""
    return {
        '_uuid': uid,
        '_id': 3,
        'Date_des_transferts': '2026-08-18',
        'group_ln06g44/Colline': KOBO_COLLINE,
        'Nom_de_l_agence_de_paiement': AGENCY,
        'group_tr1pf23/group_gl1wf27/Femme': '5',
        'group_tr1pf23/group_gl1wf27/Homme': '2',
        'group_tr1pf23/group_gl1wf27/Twa': '1',
        'group_tr1pf23/group_ee8rm46/Femme_001': paid_women,
        'group_tr1pf23/group_ee8rm46/Homme_001': '2',
        'group_tr1pf23/group_ee8rm46/Twa_001': '1',
    }


class MonetaryTransferAmountsSurviveResyncTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        province = create_test_location('D', custom_props={'code': '99', 'name': 'Province99'})
        commune = create_test_location('W', custom_props={'code': '9906', 'name': 'Commune9906',
                                                          'parent': province})
        cls.colline = create_test_location('V', custom_props={'code': IMIS_COLLINE, 'name': 'Colline990607',
                                                              'parent': commune})
        cls.agency = PaymentAgency.objects.create(code='KOBOTEST', name=AGENCY)
        cls.plan = BenefitPlan.objects.filter(code='1.2').first()
        if cls.plan is None:
            cls.plan = BenefitPlan(code='1.2', name='Plan 1.2 test', max_beneficiaries=0,
                                   type='GROUP', date_valid_from=datetime.date(2020, 1, 1),
                                   date_valid_to=datetime.date(2030, 1, 1))
            cls.plan.save(user=create_test_interactive_user(username='kobo_mt_admin'))

    def test_the_amounts_entered_in_the_mis_are_kept_and_the_counts_updated(self):
        uid = str(uuid.uuid4())
        with patch('kobo_etl.services.KoboServices.get', return_value={'results': [_submission(uid)]}):
            KoboServices.sync_monetary_transfer(None, None)
        MonetaryTransfer.objects.filter(id=uid).update(
            planned_amount=Decimal('1500000.00'), transferred_amount=Decimal('1440000.00'))

        with patch('kobo_etl.services.KoboServices.get',
                   return_value={'results': [_submission(uid, paid_women='6')]}):
            result = KoboServices.sync_monetary_transfer(None, None)

        transfer = MonetaryTransfer.objects.get(id=uid)
        self.assertEqual(result.updated, 1)
        self.assertEqual(transfer.paid_women, 6)
        self.assertEqual(transfer.planned_amount, Decimal('1500000.00'))
        self.assertEqual(transfer.transferred_amount, Decimal('1440000.00'))

    def test_the_amounts_are_not_kobo_owned(self):
        owned = KoboServices.kobo_owned_fields(MonetaryTransfer)

        self.assertNotIn('planned_amount', owned)
        self.assertNotIn('transferred_amount', owned)
        self.assertIn('paid_women', owned)


class AllScopeLeavesMonetaryTransfersOutTest(TestCase):

    def test_the_all_scope_is_every_scope_but_monetary_transfer(self):
        self.assertEqual(KoboServices.ALL_SCOPES,
                         ('grievance', 'training', 'promotion', 'micro_project'))

    def test_the_mutation_scope_all_does_not_pull_monetary_transfers(self):
        user = Mock(id=1, username='test-user')
        user.has_perms.return_value = True
        syncs = {scope: Mock(return_value=KoboServices.SyncResult()) for scope in KoboServices.SCOPE_SYNCS}

        with patch.multiple(KoboServices, sync_grievance=syncs['grievance'],
                            sync_training=syncs['training'], sync_bcpromotion=syncs['promotion'],
                            sync_micro_project=syncs['micro_project'],
                            sync_monetary_transfer=syncs['monetary_transfer']):
            result = RunKoboETLMutation.async_mutate(user, scope='all', start_date=None, end_date=None)

        self.assertIsNone(result)
        syncs['monetary_transfer'].assert_not_called()
        for scope in KoboServices.ALL_SCOPES:
            syncs[scope].assert_called_once_with(None, None)

    def test_the_command_scope_all_does_not_pull_monetary_transfers(self):
        syncs = {scope: Mock(return_value=KoboServices.SyncResult()) for scope in KoboServices.SCOPE_SYNCS}

        with patch.dict(KoboServices.SCOPE_SYNCS, syncs):
            call_command('pullkobodata', 'all', stdout=StringIO(), stderr=StringIO())

        syncs['monetary_transfer'].assert_not_called()
        for scope in KoboServices.ALL_SCOPES:
            syncs[scope].assert_called_once_with(None, None, dry_run=False)

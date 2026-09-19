from unittest.mock import Mock, patch

from django.test import TestCase

from kobo_etl.schema import RunKoboETLMutation


def _mock_user():
    user = Mock()
    user.id = 1
    user.username = "test-user"
    user.has_perms.return_value = True
    return user


class RunKoboETLMutationSyncArgsTest(TestCase):
    """RunKoboETLMutation.async_mutate must call each sync_* with (start_date, end_date)."""

    @patch("kobo_etl.services.KoboServices.sync_monetary_transfer")
    @patch("kobo_etl.services.KoboServices.sync_micro_project")
    @patch("kobo_etl.services.KoboServices.sync_bcpromotion")
    @patch("kobo_etl.services.KoboServices.sync_training")
    @patch("kobo_etl.services.KoboServices.sync_grievance")
    def test_scope_all_passes_dates_to_every_sync(
        self, sync_grievance, sync_training, sync_bcpromotion,
        sync_micro_project, sync_monetary_transfer,
    ):
        result = RunKoboETLMutation.async_mutate(
            _mock_user(), scope="all", start_date="2026-01-01", end_date="2026-01-31",
        )

        self.assertIsNone(result)
        sync_grievance.assert_called_once_with("2026-01-01", "2026-01-31")
        sync_training.assert_called_once_with("2026-01-01", "2026-01-31")
        sync_bcpromotion.assert_called_once_with("2026-01-01", "2026-01-31")
        sync_micro_project.assert_called_once_with("2026-01-01", "2026-01-31")
        sync_monetary_transfer.assert_called_once_with("2026-01-01", "2026-01-31")

    @patch("kobo_etl.services.KoboServices.sync_monetary_transfer")
    def test_scope_monetary_transfer_passes_dates(self, sync_monetary_transfer):
        result = RunKoboETLMutation.async_mutate(
            _mock_user(), scope="monetary_transfer", start_date=None, end_date=None,
        )

        self.assertIsNone(result)
        sync_monetary_transfer.assert_called_once_with(None, None)

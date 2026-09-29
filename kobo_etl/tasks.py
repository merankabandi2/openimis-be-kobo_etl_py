import logging

from celery import shared_task

from kobo_etl.services.KoboServices import KoboSyncError, run_syncs

logger = logging.getLogger(__name__)

# Scopes pulled by the nightly schedule when the beat entry gives none.
NIGHTLY_SCOPES = ("grievance", "training", "promotion", "micro_project")


@shared_task(name="kobo_etl.tasks.pull_kobo_data")
def pull_kobo_data(scopes=NIGHTLY_SCOPES):
    """Pull every submission of the given scopes; each scope runs even if a previous one failed.

    Raises KoboSyncError naming the failed scopes, so the task ends in FAILURE.
    """
    results, failures = run_syncs(list(scopes))
    for scope, result in results.items():
        logger.info(f"KoBo pull {scope}: {result}")
    if failures:
        raise KoboSyncError(f"KoBo pull failed for: {', '.join(failures)}")
    return {scope: str(result) for scope, result in results.items()}

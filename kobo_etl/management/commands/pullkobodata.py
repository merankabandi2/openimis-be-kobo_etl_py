import datetime

from django.core.management.base import BaseCommand, CommandError
from kobo_etl.management.utiils import set_logger

from kobo_etl.services.KoboServices import ALL_SCOPES, DRY_RUN_SCOPES, SCOPE_SYNCS, run_syncs

logger = set_logger()


def _date(value):
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise CommandError(f"Invalid date {value!r}, expected YYYY-MM-DD")


class Command(BaseCommand):
    help = (
        "Download the submissions of the KoBo forms of a scope and upsert them in the MIS tables. "
        "Exits with status 1 when any scope fails."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            dest="verbose",
            help="Be verbose about what it is doing",
        )
        parser.add_argument(
            "scope",
            nargs=1,
            choices=["all", *SCOPE_SYNCS],
        )
        parser.add_argument(
            "--from",
            dest="start_date",
            help="First KoBo submission day (_submission_time, UTC), YYYY-MM-DD, included",
        )
        parser.add_argument(
            "--to",
            dest="end_date",
            help="Last KoBo submission day (_submission_time, UTC), YYYY-MM-DD, included",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help=f"Fetch and convert without writing; available for {', '.join(DRY_RUN_SCOPES)}",
        )

    def handle(self, *args, **options):
        scope = options["scope"][0]
        start_date = _date(options["start_date"]) if options.get("start_date") else None
        end_date = _date(options["end_date"]) if options.get("end_date") else None
        if start_date and end_date and start_date > end_date:
            raise CommandError("--from must not be after --to")
        dry_run = options.get("dry_run", False)
        scopes = ALL_SCOPES if scope == "all" else [scope]
        if dry_run and any(s not in DRY_RUN_SCOPES for s in scopes):
            raise CommandError(f"--dry-run is available for {', '.join(DRY_RUN_SCOPES)} only")

        logger.info("Start sync Kobo %s from %s to %s%s", scope, start_date or "-", end_date or "-",
                    " (dry run)" if dry_run else "")
        results, failures = run_syncs(scopes, start_date, end_date, dry_run=dry_run)
        for name, result in results.items():
            self.stdout.write(f"{name}: {result}")
        for name, exc in failures.items():
            self.stderr.write(f"{name}: FAILED ({type(exc).__name__}: {exc})")
        if failures:
            raise CommandError(f"KoBo sync failed for: {', '.join(failures)}")
        logger.info("sync Kobo done")

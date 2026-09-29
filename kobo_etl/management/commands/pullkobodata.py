from django.core.management.base import BaseCommand, CommandError
from kobo_etl.management.utiils import set_logger

from kobo_etl.services.KoboServices import DRY_RUN_SCOPES, run_syncs

logger = set_logger()

# Scopes run by "all", in this order.
ALL_SCOPES = ["grievance", "training", "promotion", "micro_project", "monetary_transfer"]


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
            choices=["all", *ALL_SCOPES],
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help=f"Fetch and convert without writing; available for {', '.join(DRY_RUN_SCOPES)}",
        )

    def handle(self, *args, **options):
        scope = options["scope"][0]
        dry_run = options.get("dry_run", False)
        scopes = ALL_SCOPES if scope == "all" else [scope]
        if dry_run and any(s not in DRY_RUN_SCOPES for s in scopes):
            raise CommandError(f"--dry-run is available for {', '.join(DRY_RUN_SCOPES)} only")

        logger.info("Start sync Kobo %s%s", scope, " (dry run)" if dry_run else "")
        results, failures = run_syncs(scopes, dry_run=dry_run)
        for name, result in results.items():
            if result is not None:
                self.stdout.write(f"{name}: {result}")
        for name, exc in failures.items():
            self.stderr.write(f"{name}: FAILED ({type(exc).__name__}: {exc})")
        if failures:
            raise CommandError(f"KoBo sync failed for: {', '.join(failures)}")
        logger.info("sync Kobo done")

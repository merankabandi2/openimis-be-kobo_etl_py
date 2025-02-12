import datetime

from django.core.management.base import BaseCommand
from kobo_etl.management.utiils import set_logger

from kobo_etl.services.GrievanceServices import *

logger = set_logger()


class Command(BaseCommand):
    help = (
        "This command will download the data from kobo and save it in Django models."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            dest="verbose",
            help="Be verbose about what it is doing",
        )
        # parser.add_argument(
        #     "start_date",
        #     nargs=1,
        #     type=lambda s: datetime.datetime.strptime(s, "%Y-%m-%d"),
        #     required=False
        # )
        # parser.add_argument(
        #     "stop_date",
        #     nargs=1,
        #     type=lambda s: datetime.datetime.strptime(s, "%Y-%m-%d"),
        #     required=False
        # )
        parser.add_argument(
            "scope",
            nargs=1,
            choices=[
                "all",
                "grievance",
            ],
        )

    def handle(self, *args, **options):
        # start_date = options["start_date"][0]
        # stop_date = options["stop_date"][0]
        start_date = None
        stop_date = None
        scope = options["scope"][0]
        if scope is None:
            scope = "all"
        logger.info("Start sync Kobo %s ", __package__)
        self.sync_kobo(start_date, stop_date, scope)
        logger.info("sync Kobo done")

    def sync_kobo(self, start_date, stop_date, scope):
        logger.info("Received task")
        # grievance
        if scope == "grievance":
            sync_grievance(start_date, stop_date)
        logger.info("Finishing task")

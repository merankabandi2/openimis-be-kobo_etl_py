import datetime

from django.core.management.base import BaseCommand
from kobo_etl.management.utiils import set_logger

from kobo_etl.services.KoboServices import *

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
                "training",
                "promotion",
                "micro_project",
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
        match scope:
            case "grievance":
                sync_grievance(start_date, stop_date)
            case "training":
                sync_training(start_date, stop_date)
            case "promotion":
                sync_bcpromotion(start_date, stop_date)
            case "micro_project":
                sync_micro_project(start_date, stop_date)
            case "all":
                sync_grievance(start_date, stop_date)
                sync_training(start_date, stop_date)
                sync_bcpromotion(start_date, stop_date)
                sync_micro_project(start_date, stop_date)
            case _:
                logger.warning("Unknown scope: %s", scope)
        logger.info("Finishing task")

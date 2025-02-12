# Service to pull openIMIS grievance from Kobo
import logging

from grievance_social_protection.models import Ticket

from kobo_etl.builders.kobo.GrievanceConverter import GrievanceConverter
from kobo_etl.strategy.kobo_client import *

logger = logging.getLogger(__name__)

def sync_grievance(startDate, stopDate):
    koboFormData = get("aeAgbxjy7d6rD8jtUdMD9Z").get('results')
    grievances = GrievanceConverter.to_data_set_obj(koboFormData)
    Ticket.objects.bulk_create(grievances)
    return

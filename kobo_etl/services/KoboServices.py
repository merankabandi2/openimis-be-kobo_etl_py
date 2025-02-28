# Service to pull openIMIS grievance from Kobo
import logging

from kobo_etl.builders.kobo.MicroProjectConverter import MicroProjectConverter
from merankabandi.models import MicroProject, SensitizationTraining, BehaviorChangePromotion
from grievance_social_protection.models import Ticket

from kobo_etl.builders.kobo.SensitizationTrainingConverter import SensitizationTrainingConverter
from kobo_etl.builders.kobo.BehaviorChangePromotionConverter import BehaviorChangePromotionConverter
from kobo_etl.builders.kobo.GrievanceConverter import GrievanceConverter
from kobo_etl.strategy.kobo_client import *

logger = logging.getLogger(__name__)

def sync_grievance(startDate, stopDate):
    koboFormData = get("aeAgbxjy7d6rD8jtUdMD9Z").get('results')
    grievances = GrievanceConverter.to_data_set_obj(koboFormData)
    Ticket.objects.bulk_create(grievances)
    return

def sync_training(startDate, stopDate):
    koboFormData = get("a77BL33LXCfAVovg4seMbH").get('results')
    trainings = SensitizationTrainingConverter.to_data_set_obj(koboFormData)
    SensitizationTraining.objects.bulk_create(trainings)
    return

def sync_bcpromotion(startDate, stopDate):
    koboFormData = get("aMzfPosq2VNg3fHdpBJ3jU").get('results')
    trainings = BehaviorChangePromotionConverter.to_data_set_obj(koboFormData)
    BehaviorChangePromotion.objects.bulk_create(trainings)
    return

def sync_micro_project(startDate, stopDate):
    koboFormData = get("aGMbKXkL2XUhtUAmEf95es").get('results')
    trainings = MicroProjectConverter.to_data_set_obj(koboFormData)
    MicroProject.objects.bulk_create(trainings)
    return

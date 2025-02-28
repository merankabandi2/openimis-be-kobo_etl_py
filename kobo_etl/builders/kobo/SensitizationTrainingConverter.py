import logging

from merankabandi.models import SensitizationTraining
from . import BaseKoboConverter

logger = logging.getLogger('openIMIS')

class SensitizationTrainingConverter(BaseKoboConverter):

    @classmethod
    def to_data_element_obj(cls, koboData, **kwargs):
        return SensitizationTraining.to_data_element_obj(koboData)

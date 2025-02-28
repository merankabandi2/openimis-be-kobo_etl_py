import logging

from merankabandi.models import MicroProject
from . import BaseKoboConverter

logger = logging.getLogger('openIMIS')

class MicroProjectConverter(BaseKoboConverter):

    @classmethod
    def to_data_element_obj(cls, koboData, **kwargs):
        return MicroProject.to_data_element_obj(koboData)

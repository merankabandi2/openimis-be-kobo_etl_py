import logging

from merankabandi.models import BehaviorChangePromotion
from . import BaseKoboConverter

logger = logging.getLogger('openIMIS')

class BehaviorChangePromotionConverter(BaseKoboConverter):

    @classmethod
    def to_data_element_obj(cls, koboData, **kwargs):
        return BehaviorChangePromotion.to_data_element_obj(koboData)

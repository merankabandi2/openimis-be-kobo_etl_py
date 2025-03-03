import logging

from merankabandi.models import MonetaryTransfer
from . import BaseKoboConverter

logger = logging.getLogger('openIMIS')

class MonetaryTransferConverter(BaseKoboConverter):

    @classmethod
    def to_data_element_obj(cls, koboData, **kwargs):
        return MonetaryTransfer.to_data_element_obj(koboData)

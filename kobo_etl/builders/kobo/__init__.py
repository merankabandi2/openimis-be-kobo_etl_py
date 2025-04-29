import re
from abc import ABC


class BaseKoboConverter(ABC):

    @classmethod
    def to_data_element_obj(cls, koboData, **kwargs):
        raise NotImplementedError('`to_data_element_obj()` must be implemented.')  # pragma: no cover

    @classmethod
    def to_data_set_obj(cls, koboDatas, **kwargs):
        return [obj for koboData in koboDatas
                if (obj := cls.to_data_element_obj(koboData, **kwargs)) is not None and 
                (not hasattr(obj.__class__, 'location') or hasattr(obj, 'location'))]
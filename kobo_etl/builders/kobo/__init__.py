import re
from abc import ABC


class BaseKoboConverter(ABC):

    @classmethod
    def to_data_element_obj(cls, koboData, **kwargs):
        raise NotImplementedError('`to_data_element_obj()` must be implemented.')  # pragma: no cover

    @classmethod
    def to_data_set_obj(cls, koboDatas, **kwargs):
        return [cls.to_data_element_obj(koboData) for koboData in koboDatas]

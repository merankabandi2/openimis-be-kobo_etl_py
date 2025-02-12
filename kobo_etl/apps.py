import logging

from django.apps import AppConfig

MODULE_NAME = "kobo_etl"

logger = logging.getLogger(__name__)

DEFAULT_CFG = {}

class KoboConfig(AppConfig):
    name = MODULE_NAME

    def ready(self):
        from core.models import ModuleConfiguration

        cfg = ModuleConfiguration.get_or_default(MODULE_NAME, DEFAULT_CFG)
        self.__configure_module(cfg)

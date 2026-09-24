import logging

from django.apps import AppConfig

MODULE_NAME = "kobo_etl"

logger = logging.getLogger(__name__)

DEFAULT_CFG = {}

# MutationLog has no module or class column: RunKoboETLMutation logs are tagged in json_ext
# with these keys (see schema.on_kobo_etl_mutation) so the last run can be looked up.
RUN_ETL_MUTATION_CLASS = "RunKoboETLMutation"
RUN_ETL_MUTATION_LOG_TAG = {"mutation_module": MODULE_NAME, "mutation_class": RUN_ETL_MUTATION_CLASS}

class KoboConfig(AppConfig):
    name = MODULE_NAME

    # GraphQL settings
    gql_query_kobo_etl_status_perms = ['180001']
    gql_mutation_run_kobo_etl_perms = ['180002']

    def ready(self):
        from core.models import ModuleConfiguration

        cfg = ModuleConfiguration.get_or_default(MODULE_NAME, DEFAULT_CFG)

        self.__load_config(cfg)

    @classmethod
    def __load_config(cls, cfg):
        """
        Load all config fields that match current AppConfig class fields, all custom fields have to be loaded separately
        """
        for field in cfg:
            if hasattr(KoboConfig, field):
                setattr(KoboConfig, field, cfg[field])

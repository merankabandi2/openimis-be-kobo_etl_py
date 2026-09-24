import graphene
from core import ExtendedConnection
from core.models import MutationLog
from core.schema import OpenIMISMutation, signal_mutation_module_before_mutating
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from .apps import MODULE_NAME, RUN_ETL_MUTATION_CLASS, RUN_ETL_MUTATION_LOG_TAG
from .gql_queries import Query
import logging

logger = logging.getLogger(__name__)


class KoboETLScopeEnum(graphene.Enum):
    ALL = "all"
    GRIEVANCE = "grievance"
    TRAINING = "training"
    PROMOTION = "promotion"
    MICRO_PROJECT = "micro_project"
    MONETARY_TRANSFER = "monetary_transfer"


class RunKoboETLMutation(OpenIMISMutation):
    """
    Run Kobo ETL process asynchronously
    """
    _mutation_module = MODULE_NAME
    _mutation_class = RUN_ETL_MUTATION_CLASS

    class Input(OpenIMISMutation.Input):
        scope = graphene.Field(KoboETLScopeEnum, required=True)
        # Optional date range parameters for future use
        start_date = graphene.Date(required=False)
        end_date = graphene.Date(required=False)

    @classmethod
    def async_mutate(cls, user, **data):
        try:
            if type(user) is AnonymousUser or not user.id:
                raise ValidationError(_("mutation.authentication_required"))

            # Check permissions - user should have appropriate rights
            if not user.has_perms(['kobo_etl.run_etl']):
                raise ValidationError(_("unauthorized"))

            # Import here to avoid circular imports
            from kobo_etl.services.KoboServices import (
                sync_grievance, sync_training, sync_bcpromotion,
                sync_micro_project, sync_monetary_transfer
            )

            scope = data.get('scope')
            start_date = data.get('start_date')
            end_date = data.get('end_date')

            logger.info(f"Running Kobo ETL with scope: {scope} for user: {user.username}")

            # sync_* signatures require (start_date, end_date) positionally, see services/KoboServices.py
            syncs = {
                'grievance': sync_grievance,
                'training': sync_training,
                'promotion': sync_bcpromotion,
                'micro_project': sync_micro_project,
                'monetary_transfer': sync_monetary_transfer,
            }
            if scope == 'all':
                selected = list(syncs)
            elif scope in syncs:
                selected = [scope]
            else:
                raise ValidationError(f"Invalid scope: {scope}")

            # Each scope runs even if a previous one failed; any failure fails the mutation.
            errors = []
            for name in selected:
                try:
                    syncs[name](start_date, end_date)
                except Exception as exc:
                    logger.error(f"Kobo ETL sync '{name}' failed: {exc}", exc_info=True)
                    errors.append({
                        'message': _("kobo_etl.mutation.failed"),
                        'detail': f"{name}: {exc}",
                    })

            if errors:
                return errors
            logger.info(f"Kobo ETL syncs completed: {selected}")
            return None

        except Exception as exc:
            logger.error(f"Error in Kobo ETL mutation: {exc}")
            return [{
                'message': _("kobo_etl.mutation.failed"),
                'detail': str(exc)
            }]


class Mutation(graphene.ObjectType):
    run_kobo_etl = RunKoboETLMutation.Field()


def on_kobo_etl_mutation(sender, **kwargs):
    """Tag the MutationLog of a RunKoboETLMutation so koboEtlStatus.lastSyncDate can find it."""
    if kwargs.get("mutation_class") != RUN_ETL_MUTATION_CLASS:
        return []
    mutation_log = MutationLog.objects.filter(id=kwargs.get("mutation_log_id")).first()
    if mutation_log is None:
        return []
    # Queryset update: the status column is owned by core's mark_as_successful/mark_as_failed.
    MutationLog.objects.filter(id=mutation_log.id).update(
        json_ext={**(mutation_log.json_ext or {}), **RUN_ETL_MUTATION_LOG_TAG}
    )
    return []


def bind_signals():
    signal_mutation_module_before_mutating[MODULE_NAME].connect(on_kobo_etl_mutation)


# Export Query and Mutation at module level for schema loader
__all__ = ['Query', 'Mutation']
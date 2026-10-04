import graphene
from core import ExtendedConnection
from core.models import MutationLog
from core.schema import OpenIMISMutation, signal_mutation_module_before_mutating
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext as _
from .apps import KoboConfig, MODULE_NAME, RUN_ETL_MUTATION_CLASS, RUN_ETL_MUTATION_LOG_TAG
from .gql_queries import Query
import logging

logger = logging.getLogger(__name__)

# Messages of the MutationLog.error entries. The exception text can hold KoBo URLs and
# database row values, so it only goes to the server log; the entry keeps the exception
# class, prefixed with the scope when a sync of that scope failed.
KOBO_ETL_FAILED_MESSAGE = "KoBo ETL sync failed"
KOBO_ETL_UNAUTHORIZED_MESSAGE = "Unauthorized: the user may not run the KoBo ETL"


def _failure(exc, scope=None):
    """MutationLog.error entry: detail is '<scope>: <exception class>', or the class alone without a scope.

    The FE reads a '<scope>: ' prefix as a failed sync of that scope, so errors raised
    before any sync runs (refusal, invalid scope) are built without one.
    """
    exc_class = type(exc).__name__
    return {
        'message': KOBO_ETL_UNAUTHORIZED_MESSAGE if isinstance(exc, PermissionDenied) else KOBO_ETL_FAILED_MESSAGE,
        'detail': f"{scope}: {exc_class}" if scope else exc_class,
    }


class KoboETLScopeEnum(graphene.Enum):
    ALL = "all"
    GRIEVANCE = "grievance"
    TRAINING = "training"
    PROMOTION = "promotion"
    MICRO_PROJECT = "micro_project"


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
                raise PermissionDenied(_("mutation.authentication_required"))

            # Check permissions - user should have appropriate rights
            if not user.has_perms(KoboConfig.gql_mutation_run_kobo_etl_perms):
                raise PermissionDenied(_("unauthorized"))

            # Import here to avoid circular imports
            from kobo_etl.services.KoboServices import (
                ALL_SCOPES, sync_grievance, sync_training, sync_bcpromotion, sync_micro_project,
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
            }
            if scope == 'all':
                selected = list(ALL_SCOPES)
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
                    errors.append(_failure(exc, name))

            if errors:
                return errors
            logger.info(f"Kobo ETL syncs completed: {selected}")
            return None

        except Exception as exc:
            logger.error(f"Error in Kobo ETL mutation: {exc}", exc_info=True)
            return [_failure(exc)]


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
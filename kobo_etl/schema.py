import graphene
from core import ExtendedConnection
from core.schema import OpenIMISMutation, signal_mutation_module_validate
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
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
    _mutation_module = "kobo_etl"
    _mutation_class = "RunKoboETLMutation"

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

            # Execute appropriate sync based on scope
            if scope == 'all':
                # Run all syncs
                sync_results = {
                    'grievance': sync_grievance(),
                    'training': sync_training(),
                    'promotion': sync_bcpromotion(),
                    'micro_project': sync_micro_project(),
                    'monetary_transfer': sync_monetary_transfer(),
                }
                logger.info(f"All syncs completed: {sync_results}")
            elif scope == 'grievance':
                sync_results = {'grievance': sync_grievance()}
            elif scope == 'training':
                sync_results = {'training': sync_training()}
            elif scope == 'promotion':
                sync_results = {'promotion': sync_bcpromotion()}
            elif scope == 'micro_project':
                sync_results = {'micro_project': sync_micro_project()}
            elif scope == 'monetary_transfer':
                sync_results = {'monetary_transfer': sync_monetary_transfer()}
            else:
                raise ValidationError(f"Invalid scope: {scope}")

            # Return None for success (no errors)
            return None

        except Exception as exc:
            logger.error(f"Error in Kobo ETL mutation: {exc}")
            return [{
                'message': _("kobo_etl.mutation.failed"),
                'detail': str(exc)
            }]


class Mutation(graphene.ObjectType):
    run_kobo_etl = RunKoboETLMutation.Field()


# Export Query and Mutation at module level for schema loader
__all__ = ['Query', 'Mutation']
import graphene
from graphene_django import DjangoObjectType
from core import ExtendedConnection
from django.utils.translation import gettext as _
from django.core.exceptions import PermissionDenied
from core.models import MutationLog
from kobo_etl.apps import KoboConfig, RUN_ETL_MUTATION_LOG_TAG
from kobo_etl.strategy import kobo_client


def _etl_forms():
    from kobo_etl.services.KoboServices import SCOPE_FORMS
    return [uid for uids in SCOPE_FORMS.values() for uid in uids]


class KoboETLStatusType(graphene.ObjectType):
    """
    Type for returning Kobo ETL status information
    """
    is_configured = graphene.Boolean(
        description="Every KoBo form read by the ETL resolves a token and a base URL")
    is_reachable = graphene.Boolean(
        description="KoBo answers an authenticated request for the forms read by the ETL")
    has_token = graphene.Boolean()
    available_scopes = graphene.List(graphene.String)
    last_sync_date = graphene.DateTime()
    
    def resolve_is_configured(self, info):
        return kobo_client.is_configured(_etl_forms())

    def resolve_is_reachable(self, info):
        return kobo_client.is_reachable(_etl_forms())
    
    def resolve_has_token(self, info):
        from django.conf import settings
        return bool(getattr(settings, 'TOKEN_KOBO', None))
    
    def resolve_available_scopes(self, info):
        return ['all', 'grievance', 'training', 'promotion', 'micro_project', 'monetary_transfer']
    
    def resolve_last_sync_date(self, info):
        # Get the last successful ETL mutation
        last_mutation = MutationLog.objects.filter(
            **{f"json_ext__{key}": value for key, value in RUN_ETL_MUTATION_LOG_TAG.items()},
            status=MutationLog.SUCCESS
        ).order_by('-request_date_time').first()
        
        return last_mutation.request_date_time if last_mutation else None


class Query(graphene.ObjectType):
    kobo_etl_status = graphene.Field(
        KoboETLStatusType,
        description=_("Get Kobo ETL configuration and status")
    )
    
    def resolve_kobo_etl_status(self, info):
        # Check permissions
        if not info.context.user.has_perms(KoboConfig.gql_query_kobo_etl_status_perms):
            raise PermissionDenied(_("unauthorized"))
        
        return KoboETLStatusType()
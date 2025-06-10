import graphene
from graphene_django import DjangoObjectType
from core import ExtendedConnection
from django.utils.translation import gettext as _
from django.core.exceptions import PermissionDenied
from core.models import MutationLog


class KoboETLStatusType(graphene.ObjectType):
    """
    Type for returning Kobo ETL status information
    """
    is_configured = graphene.Boolean()
    has_token = graphene.Boolean()
    available_scopes = graphene.List(graphene.String)
    last_sync_date = graphene.DateTime()
    
    def resolve_is_configured(self, info):
        from django.conf import settings
        return hasattr(settings, 'TOKEN_KOBO')
    
    def resolve_has_token(self, info):
        from django.conf import settings
        return bool(getattr(settings, 'TOKEN_KOBO', None))
    
    def resolve_available_scopes(self, info):
        return ['all', 'grievance', 'training', 'promotion', 'micro_project', 'monetary_transfer']
    
    def resolve_last_sync_date(self, info):
        # Get the last successful ETL mutation
        last_mutation = MutationLog.objects.filter(
            mutation_module='kobo_etl',
            mutation_class='RunKoboETLMutation',
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
        if not info.context.user.has_perms(['kobo_etl.view_etl_status']):
            raise PermissionDenied(_("unauthorized"))
        
        return KoboETLStatusType()
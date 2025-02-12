from datetime import datetime
import logging
from core.models import User
from grievance_social_protection.models import Ticket

from . import BaseKoboConverter

logger = logging.getLogger('openIMIS')

class GrievanceConverter(BaseKoboConverter):

    @classmethod
    def to_data_element_obj(cls, grievanceKoboData, **kwargs):
        user = User.objects.get(id='17bf084f-9aa9-4eb3-a1f1-b2a6dcc3ec03')
        return Ticket(\
            id = grievanceKoboData.get('_uuid'),\
            title = grievanceKoboData.get('id_plainte'),\
            description = grievanceKoboData.get('description_plainte'),\
            code = grievanceKoboData.get('code_date') + grievanceKoboData.get('group_im0ri26/zone'),\
            channel = grievanceKoboData.get('canaux'),\
            status = 'OPEN' if grievanceKoboData.get('plainte_resolue') == 'non' else 'RESOLVED',\
            date_of_incident = datetime.fromisoformat(grievanceKoboData.get('start')),\
            user_created = user,\
            user_updated = user
            )


    @classmethod
    def to_data_set_obj(cls, grievancesKoboData, **kwargs):
        grievances = [] 
        for grievanceKoboData in grievancesKoboData:
            grievances.append(cls.to_data_element_obj(grievanceKoboData))
        return grievances


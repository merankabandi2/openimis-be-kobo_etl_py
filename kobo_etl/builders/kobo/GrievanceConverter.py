from datetime import datetime
import logging
import json
from core.models import User
from grievance_social_protection.models import Ticket

from . import BaseKoboConverter

logger = logging.getLogger('openIMIS')

class GrievanceConverter(BaseKoboConverter):

    @classmethod
    def to_data_element_obj(cls, grievanceKoboData, **kwargs):
        user = User.objects.get(id='17bf084f-9aa9-4eb3-a1f1-b2a6dcc3ec03')
        
        # Determine main category based on form selections
        categories = []
        if grievanceKoboData.get('group_categorie/categories_sensibles'):
            categories.append(grievanceKoboData.get('group_categorie/categories_sensibles'))
        if grievanceKoboData.get('group_categorie/categories_speciales'):
            categories.append(grievanceKoboData.get('group_categorie/categories_speciales'))
        if grievanceKoboData.get('group_categorie/categories_non_sensibles'):
            categories.append(grievanceKoboData.get('group_categorie/categories_non_sensibles'))
        
        # Determine flags for sensitive cases
        flags = []
        if grievanceKoboData.get('group_categorie/categories_sensibles'):
            flags.append('SENSITIVE')
        if grievanceKoboData.get('group_categorie/categories_speciales'):
            flags.append('SPECIAL')
        
        # Determine other channel if specified
        channel = grievanceKoboData.get('canaux')
        other_channel = grievanceKoboData.get('si_autre_canal_pr_ciser') if channel == 'autre' else None
        
        # Handle specific subcategories
        vbg_type = None
        if grievanceKoboData.get('group_categorie/categories_sensibles') == 'violence_vbg':
            vbg_type = grievanceKoboData.get('groupe_violence_vbg/categories_violence_vbg')
        
        exclusion_type = None
        if grievanceKoboData.get('group_categorie/categories_speciales') == 'erreur_exclusion':
            exclusion_type = grievanceKoboData.get('groupe_erreur_exclusion/categorie_erreur_exclusion')
        
        payment_type = None
        if grievanceKoboData.get('group_categorie/categories_non_sensibles') == 'paiement':
            payment_type = grievanceKoboData.get('groupe_paiements/categorie_paiements')
        
        phone_type = None
        if grievanceKoboData.get('group_categorie/categories_non_sensibles') == 'telephone':
            phone_type = grievanceKoboData.get('groupe_telephone/categorie_telephone')
        
        account_type = None
        if grievanceKoboData.get('group_categorie/categories_non_sensibles') == 'compte':
            account_type = grievanceKoboData.get('groupe_compte/categorie_compte')
        
        return Ticket(
            id = grievanceKoboData.get('_uuid'),
            title = grievanceKoboData.get('id_plainte'),
            description = grievanceKoboData.get('description_plainte'),
            code = grievanceKoboData.get('code_date') + grievanceKoboData.get('group_im0ri26/zone'),
            
            # Reporter details
            is_beneficiary = grievanceKoboData.get('est_beneficiaire'),
            non_beneficiary_details = grievanceKoboData.get('pas_beneficiaire_details'),
            gender = grievanceKoboData.get('genre_plaignant'),
            is_batwa = grievanceKoboData.get('est_autochtone_batwa'),
            beneficiary_type = grievanceKoboData.get('type_beneficiaire'),
            other_beneficiary_type = grievanceKoboData.get('Autre_type_de_b_n_ficiaire'),
            is_anonymous = grievanceKoboData.get('est_anonyme'),
            reporter_name = grievanceKoboData.get('nom_plaignant'),
            reporter_phone = grievanceKoboData.get('tel_plaignant'),
            cni_number = grievanceKoboData.get('numero_cni'),
            
            # Location details
            gps_location = grievanceKoboData.get('group_im0ri26/Localisation'),
            province = grievanceKoboData.get('group_im0ri26/province'),
            commune = grievanceKoboData.get('group_im0ri26/commune'),
            zone = grievanceKoboData.get('group_im0ri26/zone'),
            colline = grievanceKoboData.get('group_im0ri26/colline'),
            
            # Complaint details
            is_project_related = grievanceKoboData.get('projet_plainte'),
            
            # Category details
            category = json.dumps(categories) if categories else None,
            flags = json.dumps(flags) if flags else None,
            
            # Additional details for categories
            # sensitive_detail = grievanceKoboData.get('group_categorie/autre_details_sensible'),
            # special_detail = grievanceKoboData.get('group_categorie/autre_details_speciaux'),
            # non_sensitive_detail = grievanceKoboData.get('group_categorie/autre_details_non_sensible'),
            
            # Subcategory details
            vbg_type = vbg_type,
            vbg_detail = grievanceKoboData.get('groupe_violence_vbg/autre_details_violence_vbg'),
            viol_hospital = grievanceKoboData.get('groupe_viol/viol_hopital'),
            viol_complaint = grievanceKoboData.get('groupe_viol/viol_plainte'),
            viol_support = grievanceKoboData.get('groupe_viol/viol_psychosociale_economique'),
            
            exclusion_type = exclusion_type,
            exclusion_detail = grievanceKoboData.get('groupe_erreur_exclusion/autre_details_erreur_exclusion'),
            
            payment_type = payment_type,
            payment_detail = grievanceKoboData.get('groupe_paiements/autre_details_paiements'),
            
            phone_type = phone_type,
            phone_detail = grievanceKoboData.get('groupe_telephone/autre_details_telephone'),
            
            account_type = account_type,
            account_detail = grievanceKoboData.get('groupe_compte/autre_details_compte'),
            
            # Submission and resolution details
            channel = channel,
            other_channel = other_channel,
            
            receiver_name = grievanceKoboData.get('nom_recepteur'),
            receiver_function = grievanceKoboData.get('fonction_recepteur'),
            receiver_phone = grievanceKoboData.get('tel_recepteur'),
            
            is_resolved = grievanceKoboData.get('plainte_resolue'),
            resolver_name = grievanceKoboData.get('traiteur_plainte'),
            resolver_function = grievanceKoboData.get('Quelle_est_sa_fonction'),
            resolution_details = grievanceKoboData.get('details_resolution'),
            
            # Form metadata
            form_id = 'aeAgbxjy7d6rD8jtUdMD9Z',  # Form ID from the XML
            code_date = grievanceKoboData.get('code_date'),
            
            # Status based on resolution
            status = 'OPEN' if grievanceKoboData.get('plainte_resolue') == 'non' else 'RESOLVED',
            date_of_incident = datetime.fromisoformat(grievanceKoboData.get('start')),
            
            # System fields
            user_created = user,
            user_updated = user
        )

    @classmethod
    def to_data_set_obj(cls, grievancesKoboData, **kwargs):
        """
        Converts a list of Kobo grievance data into a list of data element objects.

        Args:
            grievancesKoboData (list): A list of Kobo grievance data dictionaries.
            **kwargs: Additional keyword arguments.

        Returns:
            list: A list of data element objects created from the Kobo grievance data.
        """
        return [obj for grievanceKoboData in grievancesKoboData 
            if (obj := cls.to_data_element_obj(grievanceKoboData, **kwargs)) is not None and (not hasattr(obj.__class__, 'location') or obj.location is not None)]


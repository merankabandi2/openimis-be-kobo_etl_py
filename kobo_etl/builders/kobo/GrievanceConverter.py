import logging
import json
import os
from datetime import datetime

from core.models import User
from grievance_social_protection.models import Ticket
from location.models import Location

from . import BaseKoboConverter


def _resolve_colline(colline_value):
    """Resolve a colline value (name or code) to colline_code + location_id."""
    if not colline_value:
        return {}

    colline_str = str(colline_value).strip()

    # Try KoBo→openIMIS code conversion
    if colline_str.isdigit():
        padded = colline_str.zfill(7)
        imis_code = padded[:4] + padded[5:]
        loc = Location.objects.filter(code=imis_code, type='V').first()
        if loc:
            return {'colline_code': loc.code, 'location_id': str(loc.id)}
        loc = Location.objects.filter(code=colline_str, type='V').first()
        if loc:
            return {'colline_code': loc.code, 'location_id': str(loc.id)}

    # Try name match
    loc = Location.objects.filter(name__iexact=colline_str, type='V').first()
    if loc:
        return {'colline_code': loc.code, 'location_id': str(loc.id)}

    return {}

logger = logging.getLogger('openIMIS')


def _get_import_user():
    user_id = os.environ.get('KOBO_IMPORT_USER_ID')
    if user_id:
        return User.objects.get(id=user_id)
    username = os.environ.get('KOBO_IMPORT_USERNAME')
    if username:
        return User.objects.get(username=username)
    return User.objects.first()


class GrievanceConverter(BaseKoboConverter):

    @classmethod
    def to_data_element_obj(cls, grievanceKoboData, **kwargs):
        user = _get_import_user()

        # Resolve category to a single plain string matching module config.
        # Old form allows multi-select across 3 groups (sensitive, special, non-sensitive).
        # Collect all raw values, resolve to config categories, pick most restrictive.
        from merankabandi.converters.category_resolver import (
            resolve_categories, derive_flags_from_category,
        )
        raw_category_values = []
        if grievanceKoboData.get('group_categorie/categories_sensibles'):
            raw_category_values.append(grievanceKoboData.get('group_categorie/categories_sensibles'))
        if grievanceKoboData.get('group_categorie/categories_speciales'):
            raw_category_values.append(grievanceKoboData.get('group_categorie/categories_speciales'))
        if grievanceKoboData.get('group_categorie/categories_non_sensibles'):
            raw_category_values.append(grievanceKoboData.get('group_categorie/categories_non_sensibles'))

        main_category, additional_categories, _ = resolve_categories(raw_category_values)
        flags_str = derive_flags_from_category(main_category)

        # Handle specific subcategories
        channel = grievanceKoboData.get('canaux')
        other_channel = grievanceKoboData.get('si_autre_canal_pr_ciser') if channel == 'autre' else None

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

        # Resolve location from colline value
        resolved_loc = _resolve_colline(grievanceKoboData.get('group_im0ri26/colline'))

        # Build json_ext with all custom data (columns were dropped from Ticket model)
        json_ext = {
            "form_version": "2025_v1",
            "form_id": "aeAgbxjy7d6rD8jtUdMD9Z",
            "case_type": "cas_de_r_clamation",
            "reporter": {
                "is_beneficiary": grievanceKoboData.get('est_beneficiaire'),
                "beneficiary_type": grievanceKoboData.get('type_beneficiaire'),
                "other_beneficiary_type": grievanceKoboData.get('Autre_type_de_b_n_ficiaire'),
                "is_batwa": grievanceKoboData.get('est_autochtone_batwa'),
                "is_anonymous": grievanceKoboData.get('est_anonyme'),
                "name": grievanceKoboData.get('nom_plaignant'),
                "phone": grievanceKoboData.get('tel_plaignant'),
                "cni_number": grievanceKoboData.get('numero_cni'),
                "gender": grievanceKoboData.get('genre_plaignant'),
                "non_beneficiary_details": grievanceKoboData.get('pas_beneficiaire_details'),
            },
            "location": {
                "colline_code": resolved_loc.get('colline_code', ''),
                "location_id": resolved_loc.get('location_id'),
                "gps": grievanceKoboData.get('group_im0ri26/Localisation'),
            },
            "categorization": {
                "is_project_related": grievanceKoboData.get('projet_plainte'),
            },
            "submission": {
                "channels": channel,
                "other_channel": other_channel,
                "receiver_name": grievanceKoboData.get('nom_recepteur'),
                "receiver_function": grievanceKoboData.get('fonction_recepteur'),
                "receiver_phone": grievanceKoboData.get('tel_recepteur'),
            },
            "resolution_initial": {
                "is_resolved": grievanceKoboData.get('plainte_resolue'),
                "resolver_name": grievanceKoboData.get('traiteur_plainte'),
                "resolver_function": grievanceKoboData.get('Quelle_est_sa_fonction'),
                "resolution_details": grievanceKoboData.get('details_resolution'),
            },
            "legacy": {
                "vbg_type": vbg_type,
                "vbg_detail": grievanceKoboData.get('groupe_violence_vbg/autre_details_violence_vbg'),
                "viol_hospital": grievanceKoboData.get('groupe_viol/viol_hopital'),
                "viol_complaint": grievanceKoboData.get('groupe_viol/viol_plainte'),
                "viol_support": grievanceKoboData.get('groupe_viol/viol_psychosociale_economique'),
                "exclusion_type": exclusion_type,
                "exclusion_detail": grievanceKoboData.get('groupe_erreur_exclusion/autre_details_erreur_exclusion'),
                "payment_type": payment_type,
                "payment_detail": grievanceKoboData.get('groupe_paiements/autre_details_paiements'),
                "phone_type": phone_type,
                "phone_detail": grievanceKoboData.get('groupe_telephone/autre_details_telephone'),
                "account_type": account_type,
                "account_detail": grievanceKoboData.get('groupe_compte/autre_details_compte'),
            },
        }

        # Build code safely
        code_date = grievanceKoboData.get('code_date', '')
        zone = grievanceKoboData.get('group_im0ri26/zone', '')
        code = f"{code_date}{zone}" if code_date and zone else None

        # Parse date safely
        date_of_incident = None
        start = grievanceKoboData.get('start')
        if start:
            try:
                date_of_incident = datetime.fromisoformat(start).date()
            except (ValueError, TypeError):
                pass

        if additional_categories:
            json_ext['additional_categories'] = additional_categories

        return Ticket(
            id=grievanceKoboData.get('_uuid'),
            title=grievanceKoboData.get('id_plainte'),
            description=grievanceKoboData.get('description_plainte'),
            code=code,
            category=main_category,
            flags=flags_str,
            channel=channel,
            status='OPEN' if grievanceKoboData.get('plainte_resolue') == 'non' else 'RESOLVED',
            date_of_incident=date_of_incident,
            json_ext=json_ext,
            user_created=user,
            user_updated=user,
        )

    @classmethod
    def to_data_set_obj(cls, grievancesKoboData, **kwargs):
        """Convert a list of Kobo grievance data into Ticket objects."""
        items = []
        for data in grievancesKoboData:
            try:
                obj = cls.to_data_element_obj(data, **kwargs)
                if obj is not None:
                    items.append(obj)
            except Exception as e:
                logger.error(f"Failed to convert v1 grievance {data.get('_uuid')}: {e}")
        return items

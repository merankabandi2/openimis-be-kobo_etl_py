import logging
import json
import os
import re
import unicodedata
from datetime import datetime

from core.models import User
from grievance_social_protection.models import Ticket
from location.models import Location
from merankabandi.models import KoboLocationCrosswalk

from . import BaseKoboConverter


def _normalise(name):
    """Letters of a colline name, lower case, without accents."""
    text = unicodedata.normalize('NFKD', str(name or '')).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z]', '', text.lower())


def _valid_collines(**lookup):
    return list(Location.objects.filter(type='V', validity_to__isnull=True, **lookup)[:2])


def _crosswalk_code_in_zone(zone, label):
    """KoBo colline code of the crosswalk row of KoBo zone `zone` whose label is
    `label`, '' unless there is exactly one."""
    rows = KoboLocationCrosswalk.objects.filter(kobo_code__startswith=zone).values_list(
        'kobo_code', 'kobo_colline_label')
    codes = [code for code, row_label in rows
             if len(code) == len(zone) + 2 and _normalise(row_label) == label]
    return codes[0] if len(codes) == 1 else ''


def _zone_communes(zone):
    """Ids of the live MIS communes of the live collines the crosswalk gives for
    the KoBo commune of KoBo zone `zone` (the zone code without its last digit)."""
    commune = zone[:-1]
    rows = KoboLocationCrosswalk.objects.filter(
        kobo_code__startswith=commune, location__validity_to__isnull=True,
        location__parent__validity_to__isnull=True,
    ).values_list('kobo_code', 'location__parent_id')
    return {parent_id for code, parent_id in rows
            if parent_id is not None and len(code) == len(commune) + 3}


def _located(location):
    return {'colline_code': location.code, 'location_id': str(location.id)}


def _resolve_colline(colline_value, zone_value=None):
    """colline_code + location_id of the colline of a v1 submission, {} when it
    cannot be told apart.

    A number is a KoBo colline code, resolved through KoboLocationCrosswalk, or
    else the code of one valid MIS colline. A name is resolved within the KoBo
    zone code `zone_value` (KoBo commune code + zone digit): the crosswalk row of
    that zone carrying the name, else the one valid MIS colline of that name in
    the communes the crosswalk gives for the zone's KoBo commune. Without a zone,
    a name is not resolved.
    """
    if not colline_value:
        return {}
    colline_str = str(colline_value).strip()

    if colline_str.isdigit():
        loc = KoboLocationCrosswalk.resolve(colline_str)
        if loc:
            return _located(loc)
        matches = _valid_collines(code=colline_str)
        return _located(matches[0]) if len(matches) == 1 else {}

    zone = str(zone_value or '').strip()
    label = _normalise(colline_str)
    if not zone.isdigit() or not label:
        return {}
    code = _crosswalk_code_in_zone(zone, label)
    loc = KoboLocationCrosswalk.resolve(code) if code else None
    if loc:
        return _located(loc)
    communes = _zone_communes(zone)
    if not communes:
        return {}
    matches = _valid_collines(name__iexact=colline_str, parent_id__in=communes)
    return _located(matches[0]) if len(matches) == 1 else {}


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
        from merankabandi.grievance_resolution import default_resolution_for_category
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

        # Resolve location from the colline value within the submission's zone
        colline_value = grievanceKoboData.get('group_im0ri26/colline')
        zone_value = grievanceKoboData.get('group_im0ri26/zone')
        resolved_loc = _resolve_colline(colline_value, zone_value)

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
                # Form values, kept so an unresolved ticket can be located by
                # hand later; backfill_ticket_locations does not read these keys.
                "kobo_colline_label": str(colline_value).strip() if colline_value else '',
                "kobo_zone": str(zone_value).strip() if zone_value else '',
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

        ticket = Ticket(
            id=grievanceKoboData.get('_uuid'),
            title=grievanceKoboData.get('id_plainte'),
            description=grievanceKoboData.get('description_plainte'),
            code=code,
            category=main_category,
            flags=flags_str,
            channel=channel,
            resolution=default_resolution_for_category(main_category),
            status='OPEN' if grievanceKoboData.get('plainte_resolue') == 'non' else 'RESOLVED',
            date_of_incident=date_of_incident,
            json_ext=json_ext,
            user_created=user,
            user_updated=user,
        )
        # bulk_upsert inserts without pre_save: a VBG/EAS/HS ticket keeps no
        # identity (the v1 form asks no consent to store it).
        from merankabandi.grievance_vbg import minimize_ticket
        minimize_ticket(ticket, is_new=True)
        return ticket

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

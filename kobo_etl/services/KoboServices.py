# Service to pull openIMIS grievance from Kobo
import logging

from merankabandi.models import (
    BehaviorChangePromotion, KoboLocationCrosswalk, MicroProject, SensitizationTraining,
)
from grievance_social_protection.models import Ticket

from kobo_etl.builders.kobo.SensitizationTrainingConverter import SensitizationTrainingConverter
from kobo_etl.builders.kobo.BehaviorChangePromotionConverter import BehaviorChangePromotionConverter
from kobo_etl.builders.kobo.MicroProjectConverter import MicroProjectConverter
from kobo_etl.builders.kobo.GrievanceConverter import GrievanceConverter
from kobo_etl.strategy.kobo_client import *
from collections import Counter
from contextlib import nullcontext
from dataclasses import dataclass

from django.db import transaction
from django.db.models import F
from typing import List, Dict, Any, Tuple, Optional, Set

logger = logging.getLogger(__name__)

def bulk_upsert(model_class, data_list: List[Dict[Any, Any]], 
                lookup_field: str = "id", update_fields: Optional[List[str]] = None, 
                chunk_size: int = 1000) -> Tuple[int, int]:
    """
    Efficiently performs bulk upsert operations (update or insert) using Django's ORM.
    
    Args:
        model_class: The Django model class
        data_list: List of dictionaries with data to upsert
        lookup_field: Field to use for identifying existing records
        update_fields: List of fields to update when an existing record is found
                      (defaults to all model fields except primary key)
        chunk_size: Number of records to process per batch
        
    Returns:
        Tuple of (number of created records, number of updated records)
    """
    if not data_list:
        return 0, 0
    
    # If update_fields not provided, use all model fields except primary key
    if update_fields is None:
        update_fields = _get_model_fields(model_class, exclude_pk=True)
    
    created_count = 0
    updated_count = 0
    
    # Process in chunks to manage memory usage
    for i in range(0, len(data_list), chunk_size):
        chunk = data_list[i:i+chunk_size]
        created, updated = _process_chunk(model_class, chunk, lookup_field, update_fields)
        created_count += created
        updated_count += updated
    logger.info(f"Created: {created_count}, Updated: {updated_count}, Total: {len(data_list)}")
    return created_count, updated_count


def _get_model_fields(model_class, exclude_pk: bool = True) -> List[str]:
    """Get all field names from a Django model, optionally excluding primary key."""
    fields = [field.name for field in model_class._meta.fields]
    
    if exclude_pk:
        pk_name = model_class._meta.pk.name
        fields = [f for f in fields if f != pk_name]
        
    return fields


def _process_chunk(model_class, data_chunk: List[Dict[Any, Any]], 
                  lookup_field: str, update_fields: List[str]) -> Tuple[int, int]:
    """Process a single chunk of the data for upsert operation."""
    
    # Extract lookup values for filtering
    lookup_values = []
    for data in data_chunk:
        # Handle both dictionaries and model instances
        if isinstance(data, dict):
            if lookup_field in data:
                lookup_values.append(data[lookup_field])
        else:
            # Assume it's a model instance
            if hasattr(data, lookup_field):
                lookup_values.append(getattr(data, lookup_field))
    # Handle empty lookup values
    if not lookup_values:
        return 0, 0
    
    # Fetch existing objects that match lookup values
    lookup_kwargs = {f"{lookup_field}__in": lookup_values}
    existing_objects = {
        str(getattr(obj, lookup_field)): obj 
        for obj in model_class.objects.filter(**lookup_kwargs)
    }

    # Separate objects to update and create
    to_update = []
    to_create = []
    
    for data in data_chunk:
        lookup_value = None
        if isinstance(data, dict):
            if lookup_field not in data:
                continue

            lookup_value = data[lookup_field]
        else:
            # Assume it's a model instance
            if not hasattr(data, lookup_field):
                continue
            lookup_value = getattr(data, lookup_field)
            
        
        if lookup_value in existing_objects:
            # Update existing object
            obj = existing_objects[lookup_value]
            
            # Apply updates to fields
            updated = False
            for field in update_fields:
                if hasattr(data, field) and field != lookup_field:
                    setattr(obj, field, getattr(data, field))
                    updated = True
            
            if updated:
                to_update.append(obj)
        else:
            # Create new object
            to_create.append(data)
    
    # Perform bulk operations
    created_count = 0
    updated_count = 0
    
    # Bulk create new objects
    if to_create:
        model_class.objects.bulk_create(to_create)
        created_count = len(to_create)
    
    # Bulk update existing objects
    if to_update and update_fields:
        # Filter out lookup_field from update_fields if it's there
        fields_to_update = [f for f in update_fields if f != lookup_field]
        if fields_to_update:  # Only update if there are fields to update
            model_class.objects.bulk_update(to_update, fields_to_update)
            updated_count = len(to_update)
    
    return created_count, updated_count

# Columns written in the MIS after import (activity validation): a re-sync never overwrites them.
LOCALLY_OWNED_FIELDS = ('validation_status', 'validated_by', 'validation_date', 'validation_comment')
# Scopes run by "all", in this order. Monetary transfers have no KoBo scope: they are
# entered only on the MIS « Transferts Monétaires » screen.
ALL_SCOPES = ('grievance', 'training', 'promotion', 'micro_project')

# Scopes whose conversion writes nothing, so a dry run can classify their submissions.
DRY_RUN_SCOPES = ('training', 'promotion', 'micro_project')


@dataclass
class SyncResult:
    fetched: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    dry_run: bool = False

    def __str__(self):
        verb = "would be " if self.dry_run else ""
        return (f"{self.fetched} submissions fetched, {self.created} {verb}created, "
                f"{self.updated} {verb}updated, {self.skipped} skipped")


def kobo_owned_fields(model_class) -> List[str]:
    """Fields a re-sync overwrites: every non-pk field except LOCALLY_OWNED_FIELDS."""
    return [f for f in _get_model_fields(model_class) if f not in LOCALLY_OWNED_FIELDS]


def _count_existing(model_class, items, chunk_size=1000) -> int:
    ids = [item.id for item in items]
    return sum(
        model_class.objects.filter(id__in=ids[i:i + chunk_size]).count()
        for i in range(0, len(ids), chunk_size)
    )


ACTIVITY_COLLINE_FIELD = 'group_ln06g44/Colline'
ACTIVITY_COMMUNE_FIELD = 'group_ln06g44/Commune'


def _unmatched_collines_by_commune(submissions, items) -> Dict[str, List[str]]:
    """{KoBo commune code: KoBo colline codes} of the submissions the converter dropped."""
    kept = {str(item.id) for item in items}
    by_commune = {}
    for submission in submissions:
        if str(submission.get('_uuid')) in kept:
            continue
        commune = str(submission.get(ACTIVITY_COMMUNE_FIELD) or '?')
        colline = KoboLocationCrosswalk.kobo_code_of(submission.get(ACTIVITY_COLLINE_FIELD)) or '(none)'
        codes = by_commune.setdefault(commune, [])
        if colline not in codes:
            codes.append(colline)
    return by_commune


def _log_form_versions(scope, items):
    """Log, per KoBo form version, how many submissions were read and from which participant fields.

    Uses the unsaved kobo_form_version / kobo_participant_source attributes the
    converters set; submissions matching no known participant field are a WARNING.
    """
    sources = Counter((getattr(item, 'kobo_form_version', None), getattr(item, 'kobo_participant_source', None))
                      for item in items if hasattr(item, 'kobo_participant_source'))
    for (version, source), count in sorted(sources.items(), key=lambda row: (str(row[0][0]), str(row[0][1]))):
        if source:
            logger.info(f"{scope}: form version {version}: {count} submissions, participants from {source}")
    unknown = {version: count for (version, source), count in sources.items() if not source}
    if unknown:
        logger.warning(f"{scope}: {sum(unknown.values())} submissions without any known participant field, "
                       f"stored with 0 participants (form versions: {', '.join(sorted(map(str, unknown)))})")


def _sync_activity(scope, form_uid, converter, model_class, dry_run=False, after_upsert=None) -> SyncResult:
    """Fetch one activity form and upsert its submissions by KoBo _uuid.

    Submissions the converter drops (colline code without a location in
    KoboLocationCrosswalk) are counted as skipped.
    after_upsert(items), when given, runs in one transaction with the upsert.
    """
    submissions = get(form_uid).get('results', [])
    items = converter.to_data_set_obj(submissions, location_map=KoboLocationCrosswalk.location_map())
    result = SyncResult(fetched=len(submissions), skipped=len(submissions) - len(items), dry_run=dry_run)
    _log_form_versions(scope, items)
    if result.skipped:
        unmatched = _unmatched_collines_by_commune(submissions, items)
        detail = '; '.join(f"commune {commune}: {', '.join(sorted(codes))}"
                           for commune, codes in sorted(unmatched.items()))
        logger.warning(f"{scope}: {result.skipped} of {result.fetched} KoBo submissions skipped "
                       f"(no crosswalk location for their KoBo colline code) - {detail}")
    if dry_run:
        result.updated = _count_existing(model_class, items)
        result.created = len(items) - result.updated
        return result
    with transaction.atomic() if after_upsert else nullcontext():
        result.created, result.updated = bulk_upsert(
            model_class=model_class, data_list=items, update_fields=kobo_owned_fields(model_class),
        )
        if after_upsert:
            after_upsert(items)
    logger.info(f"{scope}: {result}")
    return result


def sync_grievance(startDate, stopDate, dry_run=False):
    if dry_run:
        raise ValueError("Dry run is not available for grievance: its import creates workflows")
    # Old form (v1) — legacy, still active for historical data
    # update_fields=[] means: insert new records only, never overwrite existing ones.
    # Once a ticket is in the system, local changes (status, workflow, resolution) own it.
    try:
        koboFormData = get("aeAgbxjy7d6rD8jtUdMD9Z").get('results', [])
        if koboFormData:
            items = GrievanceConverter.to_data_set_obj(koboFormData)
            bulk_upsert(model_class=Ticket, data_list=items, update_fields=[])
            logger.info(f"Synced {len(items)} grievances from old form (v1)")
    except Exception as e:
        logger.warning(f"Failed to sync old grievance form: {e}")

    # New form (v2) — 2025 restructured form with workflow support
    # Uses same bulk_upsert pattern as v1, then creates workflows after
    try:
        from merankabandi.converters.grievance_converter_v2 import GrievanceConverterV2
        new_kobo_data = get("atpoVbHXZCdLD9ETHTv6z4").get('results', [])
        if new_kobo_data:
            created, updated, wf_count = GrievanceConverterV2.import_batch(new_kobo_data)
            logger.info(f"Synced v2: {created} new, {updated} updated, {wf_count} workflows")
    except Exception as e:
        logger.warning(f"Failed to sync new grievance form: {e}", exc_info=True)

    return

def sync_training(startDate, stopDate, dry_run=False):
    return _sync_activity('training', "a77BL33LXCfAVovg4seMbH", SensitizationTrainingConverter,
                          SensitizationTraining, dry_run)

def sync_bcpromotion(startDate, stopDate, dry_run=False):
    return _sync_activity('promotion', "aMzfPosq2VNg3fHdpBJ3jU", BehaviorChangePromotionConverter,
                          BehaviorChangePromotion, dry_run)

def sync_micro_project(startDate, stopDate, dry_run=False):
    return _sync_activity('micro_project', "aGMbKXkL2XUhtUAmEf95es", MicroProjectConverter,
                          MicroProject, dry_run, after_upsert=MicroProject.replace_other_project_types)


SCOPE_SYNCS = {
    'grievance': sync_grievance,
    'training': sync_training,
    'promotion': sync_bcpromotion,
    'micro_project': sync_micro_project,
}


def run_syncs(scopes, start_date=None, end_date=None, dry_run=False):
    """Run each scope in turn, a failed scope not stopping the next ones.

    Returns ({scope: result}, {scope: exception}); a grievance result is None.
    """
    results, failures = {}, {}
    for scope in scopes:
        try:
            results[scope] = SCOPE_SYNCS[scope](start_date, end_date, dry_run=dry_run)
        except Exception as exc:
            logger.error(f"KoBo sync '{scope}' failed: {exc}", exc_info=True)
            failures[scope] = exc
    return results, failures

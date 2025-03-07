# Service to pull openIMIS grievance from Kobo
import logging

from merankabandi.models import MicroProject, MonetaryTransfer, SensitizationTraining, BehaviorChangePromotion
from grievance_social_protection.models import Ticket

from kobo_etl.builders.kobo.SensitizationTrainingConverter import SensitizationTrainingConverter
from kobo_etl.builders.kobo.BehaviorChangePromotionConverter import BehaviorChangePromotionConverter
from kobo_etl.builders.kobo.MonetaryTransferConverter import MonetaryTransferConverter
from kobo_etl.builders.kobo.MicroProjectConverter import MicroProjectConverter
from kobo_etl.builders.kobo.GrievanceConverter import GrievanceConverter
from kobo_etl.strategy.kobo_client import *
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
    print([created_count, updated_count, len(data_list)])
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

def sync_grievance(startDate, stopDate):
    koboFormData = get("aeAgbxjy7d6rD8jtUdMD9Z").get('results')
    items = GrievanceConverter.to_data_set_obj(koboFormData)
    bulk_upsert(
        model_class=Ticket,
        data_list=items
    )
    return

def sync_training(startDate, stopDate):
    koboFormData = get("a77BL33LXCfAVovg4seMbH").get('results')
    items = SensitizationTrainingConverter.to_data_set_obj(koboFormData)
    bulk_upsert(
        model_class=SensitizationTraining,
        data_list=items
    )
    return

def sync_bcpromotion(startDate, stopDate):
    koboFormData = get("aMzfPosq2VNg3fHdpBJ3jU").get('results')
    items = BehaviorChangePromotionConverter.to_data_set_obj(koboFormData)
    bulk_upsert(
        model_class=BehaviorChangePromotion,
        data_list=items
    )
    return

def sync_micro_project(startDate, stopDate):
    koboFormData = get("aGMbKXkL2XUhtUAmEf95es").get('results')
    items = MicroProjectConverter.to_data_set_obj(koboFormData)
    bulk_upsert(
        model_class=MicroProject,
        data_list=items
    )
    return

def sync_monetary_transfer(startDate, stopDate):
    koboFormData = get("ayK8Y5yP3MPTYQ3cPcpj9N").get('results')
    items = MonetaryTransferConverter.to_data_set_obj(koboFormData)
    bulk_upsert(
        model_class=MonetaryTransfer,
        data_list=items
    )
    return

def sync_rsu_partial(startDate, stopDate):
    koboFormData = get("a6rTFPVMsQKfYZKmH7RRDL").get('results')
    items = MonetaryTransferConverter.to_data_set_obj(koboFormData)
    bulk_upsert(
        model_class=MonetaryTransfer,
        data_list=items
    )
    return

def sync_rsu_all(startDate, stopDate):
    koboFormData = get("acPfASinsGorm6ojyhfJff").get('results')
    items = MonetaryTransferConverter.to_data_set_obj(koboFormData)
    bulk_upsert(
        model_class=MonetaryTransfer,
        data_list=items
    )
    return
from dataclasses import dataclass
from typing import Optional

from core.models import AuditLog, Design, User


@dataclass
class ChangeContext:
    user: User
    design: Optional[Design] = None


@dataclass
class TargetRef:
    entity: str
    entity_id: int


def log_creation(context: ChangeContext, target: TargetRef, description=""):
    AuditLog.objects.create(
        action=AuditLog.Action.CREATE,
        entity=target.entity,
        entity_id=target.entity_id,
        user=context.user,
        design=context.design,
        description=description,
    )


def log_deletion(context: ChangeContext, target: TargetRef, description=""):
    AuditLog.objects.create(
        action=AuditLog.Action.DELETE,
        entity=target.entity,
        entity_id=target.entity_id,
        user=context.user,
        design=context.design,
        description=description,
    )


def log_field_change(context: ChangeContext, target: TargetRef, field_name, old_value, new_value):
    AuditLog.objects.create(
        action=AuditLog.Action.UPDATE,
        entity=target.entity,
        entity_id=target.entity_id,
        field_name=field_name,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
        user=context.user,
        design=context.design,
    )


def diff_and_log_instance(context: ChangeContext, instance, incoming_data, tracked_fields, entity):
    changed_fields = []
    for field in tracked_fields:
        if field not in incoming_data:
            continue
        old_value = getattr(instance, field)
        new_value = incoming_data[field]
        if str(old_value) == str(new_value):
            continue

        log_field_change(context, TargetRef(entity, instance.id), field, old_value, new_value)
        setattr(instance, field, new_value)
        changed_fields.append(field)

    return changed_fields

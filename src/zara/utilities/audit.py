from datetime import datetime, timezone
from typing import TYPE_CHECKING

from zara.utilities.context import Context

if TYPE_CHECKING:
    from .database.base import Model


async def create_audit_log(model: "Model", action_type: str = "create"):
    from zara.utilities.database.models.auditlog_model import AuditLog

    if isinstance(model, AuditLog):
        return
    request = Context.get_request()
    is_system = False
    actor_id = None
    if hasattr(request, "user") and request.user is not None:
        actor_id = getattr(request.user, "id", None)
    if actor_id is None:
        is_system = True
    object_id = getattr(model, "id", None)
    object_type = model.__class__.__name__

    # Derive 'where' from request headers
    request.logger.debug(request.headers)
    where = (
        request.original_headers.get("X-Real-IP")
        or request.original_headers.get("X-Forwarded-For")
        or ""
    )

    audit_log = AuditLog(
        actor_id=actor_id,
        object_id=object_id,
        object_type=object_type,
        event_name=f"{object_type}CreatedEvent",
        description=f"New {object_type} created",
        action=f"Created {object_type}",
        action_type=action_type,
        at=datetime.now(tz=timezone.utc).replace(tzinfo=None),
        loc=where or "unknown",
        is_system=is_system,
        change_snapshot="_",
    )

    await audit_log.create()


def audit_create(func):
    async def wrapper(self, *args, **kwargs):
        result = await func(self, *args, **kwargs)
        await create_audit_log(result)
        return result

    return wrapper

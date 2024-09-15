from datetime import datetime, timezone
from typing import TYPE_CHECKING

from zara.application.events import Event
from zara.utilities.context import Context
from zara.utilities.database import AsyncDatabase

if TYPE_CHECKING:
    pass


async def create_audit_log(event: Event):
    from zara.utilities.database.models.auditlog_model import AuditLog

    if isinstance(event.data["model"], AuditLog):
        return
    request = event.data["request"]
    is_system = False
    actor_id = None
    if hasattr(request, "user") and request.user is not None:
        actor_id = getattr(request.user, "id", None)
    if actor_id is None:
        is_system = True
    object_id = getattr(event.data["model"], "id", None)
    object_type = event.data["model"].__class__.__name__

    where = (
        request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For") or ""
    )

    audit_log = AuditLog(
        actor_id=actor_id,
        object_id=object_id,
        object_type=object_type,
        event_name=f"{object_type}CreatedEvent",
        description=f"New {object_type} created",
        action=f"Created {object_type}",
        action_type=event.data["action_type"],
        at=datetime.now(tz=timezone.utc).replace(tzinfo=None),
        loc=where or "unknown",
        is_system=is_system,
        change_snapshot="_",
    )

    async with AsyncDatabase("acme_corp", backend="postgresql") as db:
        with Context.context(db, request, None):
            await audit_log.create()

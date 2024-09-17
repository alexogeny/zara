from datetime import datetime, timezone
from typing import TYPE_CHECKING

from zara.application.events import Event
from zara.utilities.context import Context
from zara.utilities.database import AsyncDatabase

if TYPE_CHECKING:
    pass


async def create_audit_log(event: Event):
    from zara.utilities.database.models.auditlog_model import AuditLog

    request = event.data["request"]
    is_system = False
    actor_id = None
    actor_id = request.get("user", {}).get("id", None)
    if actor_id is None:
        is_system = True
    object_id = event.data["model"]["id"]
    object_type = event.data["meta"]["object_type"]

    where = (
        request["headers"].get(b"X-Real-IP")
        or request["headers"].get(b"X-Forwarded-For")
        or b""
    ).decode("utf-8")

    object_action = event.data["meta"]["action_type"]
    audit_log = AuditLog(
        should_audit=False,
        actor_id=actor_id,
        object_id=object_id,
        object_type=object_type,
        event_name=f"{object_type}{object_action.title()}Event",
        description=f"New {object_type} {object_action}",
        at=datetime.now(tz=timezone.utc).replace(tzinfo=None),
        loc=where or "unknown",
        is_system=is_system,
        change_snapshot="_",
    )

    async with AsyncDatabase(
        event.data["meta"]["customer"], backend="postgresql"
    ) as db:
        with Context.context(db, request, None, event.data["meta"]["customer"]):
            await audit_log.create()

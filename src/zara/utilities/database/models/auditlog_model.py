from datetime import datetime
from typing import TYPE_CHECKING

from zara.utilities.database.base import Model
from zara.utilities.database.fields import DatabaseField, HasOne, Required
from zara.utilities.database.mixins import IdMixin

if TYPE_CHECKING:

    class Users:
        pass


class AuditLog(Model, IdMixin):
    # actor_id: the user id that performed the action
    actor_id: HasOne["Users"] = HasOne["Users"]
    # object_id: the object that was acted upon
    object_id: Required[str] = DatabaseField(nullable=False, length=30)
    # object_type: the type of object that was acted upon (the table name)
    object_type: Required[str] = DatabaseField(nullable=False)
    # event_name: the name of the event that occurred
    event_name: Required[str] = DatabaseField(nullable=False)
    # description: an event description for humans
    description: Required[str] = DatabaseField(nullable=False)
    # change_snapshot: a json object of the changes that occurred
    change_snapshot: Required[str] = DatabaseField(nullable=False)
    # when: when the action occurred
    at: Required[datetime] = DatabaseField(nullable=False)
    # where: where the action occurred eg device id or ip address
    loc: Required[str] = DatabaseField(nullable=False)
    # is_system: whether the action was performed by a system
    is_system: Required[bool] = DatabaseField(nullable=False)

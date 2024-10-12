# Example usage:

import datetime

from zara.utilities.database.orm import DatabaseField, Model, Relationship


class AuditLog(Model):
    _table_name = "auditlog"
    id = DatabaseField(primary_key=True, data_type=str, length=30)
    actor = Relationship("User", has_one="actor")
    object_id = DatabaseField(data_type=str, length=30)
    object_type = DatabaseField(data_type=str)
    event_name = DatabaseField(data_type=str)
    description = DatabaseField(data_type=str)
    change_snapshot = DatabaseField(data_type=str)
    at = DatabaseField(data_type=datetime.datetime)
    loc = DatabaseField(data_type=str)
    is_system = DatabaseField(data_type=bool)

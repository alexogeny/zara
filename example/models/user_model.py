# Example usage:

from example.models.mixins import AuditMixin, IdMixin
from zara.utilities.database.orm import DatabaseField, Model
from zara.utilities.id57 import generate_lexicographical_uuid


class User(Model, IdMixin, AuditMixin):
    _table_name = "users"

    name = DatabaseField()
    age = DatabaseField(data_type=int, nullable=True)
    password_hash = DatabaseField(private=True, nullable=True)
    token_secret = DatabaseField(
        data_type=str,
        length=30,
        default_factory=generate_lexicographical_uuid,
        private=True,
    )

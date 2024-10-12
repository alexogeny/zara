# Example usage:

from zara.utilities.database.orm import DatabaseField, Model
from zara.utilities.id57 import generate_lexicographical_uuid


class User(Model):
    _table_name = "users"

    id = DatabaseField(
        primary_key=True,
        data_type=str,
        length=30,
        default_factory=generate_lexicographical_uuid,
    )
    name = DatabaseField()
    age = DatabaseField(data_type=int, nullable=True)
    password_hash = DatabaseField(private=True, nullable=True)
    token_secret = DatabaseField(
        data_type=str,
        length=30,
        default_factory=generate_lexicographical_uuid,
        private=True,
    )

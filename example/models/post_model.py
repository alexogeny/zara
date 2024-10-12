# Example usage:

from example.models.mixins import AuditMixin
from zara.utilities.database.orm import DatabaseField, Model, Relationship
from zara.utilities.id57 import generate_lexicographical_uuid


class Post(AuditMixin, Model):
    _table_name = "posts"

    id = DatabaseField(
        primary_key=True,
        data_type=str,
        length=30,
        default_factory=generate_lexicographical_uuid,
    )
    title = DatabaseField()
    content = DatabaseField()
    author = Relationship("User", has_one="author")

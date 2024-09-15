from typing import TYPE_CHECKING

from zara.utilities.database.base import Model, Public
from zara.utilities.database.fields import DatabaseField, Optional
from zara.utilities.id57 import generate_lexicographical_uuid

if TYPE_CHECKING:

    class Users:
        pass


class PublicConfiguration(Model, Public):
    token_secret: Optional[str] = DatabaseField(
        nullable=False,
        default=lambda: generate_lexicographical_uuid(),
        auto_increment=False,
        primary_key=False,
        data_type=str,
        length=30,
        private=True,
    )

from typing import TYPE_CHECKING

from zara.utilities.database.base import Model
from zara.utilities.database.fields import DatabaseField, Optional
from zara.utilities.database.mixins import AuditMixin
from zara.utilities.id57 import generate_lexicographical_uuid

if TYPE_CHECKING:

    class Users:
        pass


class Configuration(Model, AuditMixin):
    token_secret: Optional[str] = DatabaseField(  # Base 57 timestamped uuid 4
        auto_increment=False,
        primary_key=False,
        data_type=str,
        length=30,
        default=lambda: generate_lexicographical_uuid(),
        private=True,
    )
    is_active: Optional[bool] = DatabaseField(nullable=False, default=True)
    custom_name: Optional[str] = DatabaseField(nullable=True)
    custom_logo: Optional[str] = DatabaseField(nullable=True)
    custom_color: Optional[str] = DatabaseField(nullable=True)


class OpenIDProvider(Model, AuditMixin):
    client_id: Optional[str] = DatabaseField(nullable=True)
    client_secret: Optional[str] = DatabaseField(nullable=True, private=True)
    redirect_uri: Optional[str] = DatabaseField(nullable=True)
    scope: Optional[str] = DatabaseField(nullable=True)
    issuer: Optional[str] = DatabaseField(nullable=True)
    is_active: Optional[bool] = DatabaseField(nullable=False, default=True)

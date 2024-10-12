from typing import TYPE_CHECKING

from example.models.mixins import AuditMixin, IdMixin
from zara.utilities.database.orm import DatabaseField, Model
from zara.utilities.id57 import generate_lexicographical_uuid

if TYPE_CHECKING:

    class Users:
        pass


class TenantConfig(Model, IdMixin, AuditMixin):
    _table_name = "configuration"

    token_secret = DatabaseField(
        data_type=str,
        length=30,
        default_factory=generate_lexicographical_uuid,
        private=True,
    )
    is_active = DatabaseField(nullable=False, default="True")
    custom_name = DatabaseField(nullable=True)
    custom_logo = DatabaseField(nullable=True)
    custom_color = DatabaseField(nullable=True)


class OpenIDProvider(Model, IdMixin, AuditMixin):
    _table_name = "openid_provider"

    client_id = DatabaseField(nullable=True)
    client_secret = DatabaseField(nullable=True, private=True)
    redirect_uri = DatabaseField(nullable=True)
    scope = DatabaseField(nullable=True)
    issuer = DatabaseField(nullable=True)
    is_active = DatabaseField(nullable=False, default="True")

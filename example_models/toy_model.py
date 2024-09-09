# Mixins

from zara.utilities.database.base import Model
from zara.utilities.database.fields import (
    HasOne,
    Optional,
    Required,
)
from zara.utilities.database.mixins import AuditMixin


class Toy(Model, AuditMixin):
    name: Required[str] = None
    belongs_to: HasOne["Pet"] = HasOne["Pet"]
    manufacturer: Optional[str] = None
    color: Optional[str] = None

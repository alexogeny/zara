# Mixins

from zara.utilities.database.base import Model
from zara.utilities.database.fields import (
    AutoIncrement,
    HasOne,
    Optional,
    PrimaryKey,
    Required,
)
from zara.utilities.database.mixins import MetaMixin, SoftDeleteMixin


class Toy(Model, MetaMixin, SoftDeleteMixin):
    id: AutoIncrement[PrimaryKey] = AutoIncrement()
    name: Required[str] = None
    belongs_to: HasOne["Pet"] = HasOne["Pet"]
    manufacturer: Optional[str] = None
    color: Optional[str] = None

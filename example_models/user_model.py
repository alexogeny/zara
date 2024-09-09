# Mixins

from zara.utilities.database.base import Model
from zara.utilities.database.fields import (
    AutoIncrement,
    HasMany,
    Optional,
    PrimaryKey,
    Required,
)
from zara.utilities.database.mixins import MetaMixin, SoftDeleteMixin


class User(Model, MetaMixin, SoftDeleteMixin):
    id: AutoIncrement[PrimaryKey] = AutoIncrement()
    name: Required[str] = None
    email: Optional[str] = None

    pets: HasMany["Pet"] = HasMany["Pet"]  # type: ignore  # noqa: F821

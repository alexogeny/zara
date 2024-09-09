# Mixins
import datetime

from zara.utilities.database.base import Model
from zara.utilities.database.fields import (
    AutoIncrement,
    Default,
    HasMany,
    HasOne,
    Optional,
    PrimaryKey,
    Required,
)


class MetaMixin:
    created_at: Required[datetime.datetime] = Default(
        datetime.datetime.now(tz=datetime.timezone.utc)
    )


class SoftDeleteMixin:
    deleted_at: Optional[datetime.datetime] = None


class Pet(Model, MetaMixin, SoftDeleteMixin):
    id: AutoIncrement[PrimaryKey] = AutoIncrement()
    name: Required[str] = None
    species: Optional[str] = "Dog"
    breed: Optional[str] = None
    color: Optional[str] = Default("Brown")
    age: Optional[int] = Default(0)
    current_date: Optional[datetime.datetime] = Default(
        lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )

    owner: HasOne["User"] = HasOne["User"]
    toys: HasMany["Toy"] = HasMany["Toy"]

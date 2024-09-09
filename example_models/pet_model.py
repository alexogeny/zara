# Mixins
import datetime

from zara.utilities.database.base import Model
from zara.utilities.database.fields import (
    Default,
    HasMany,
    HasOne,
    Optional,
    Required,
)
from zara.utilities.database.mixins import AuditMixin


class Pet(Model, AuditMixin):
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

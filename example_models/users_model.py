# Mixins

from zara.utilities.database.base import Model
from zara.utilities.database.mixins import (
    UsersMixin,
)


class Users(Model, UsersMixin):
    pass

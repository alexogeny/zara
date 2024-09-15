from typing import Any, Generic, TypeVar

T = TypeVar("T")


class DatabaseFieldType(Generic[T]):
    """Indicates an optional field."""

    def __init__(self, field_type: T):
        self.field_type = field_type

    @classmethod
    def __class_getitem__(cls, item):
        return cls(item)


class DatabaseField:
    def __init__(
        self,
        data_type: Any = str,
        primary_key: bool = False,
        auto_increment: bool = False,
        private: bool = False,
        unique: bool = False,
        nullable: bool = True,
        index: bool = False,
        index_type: str = "btree",
        length: int = None,
        default: Any = None,
    ):
        self.data_type = data_type
        self.primary_key = primary_key
        self.auto_increment = auto_increment
        self.private = private
        self.unique = unique
        self.nullable = nullable
        self.index = index
        self.index_type = index_type
        self.default = default
        self.length = length

    def get_value(self):
        if callable(self.default):
            return self.default()
        return self.default

    def __repr__(self):
        return f"<DatabaseField: {self.primary_key}, {self.auto_increment}, {self.private}, {self.unique}, {self.index}, {self.index_type}, {self.default}>"


class Default:
    def __init__(self, value):
        # Store the value which can be a callable or a direct value
        self.value = value

    def get_value(self):
        # If the value is callable (like datetime.now), call it to get the result
        if callable(self.value):
            return self.value()
        return self.value

    def __repr__(self):
        # For better readability when printing, you can show the value stored
        return f"Default({self.value})"


class Private:
    """Indicates a private field."""

    def __init__(self):
        pass


class Required(Generic[T]):
    """Indicates a required field."""

    def __init__(self, field_type: T):
        self.field_type = field_type

    @classmethod
    def __class_getitem__(cls, item):
        return cls(item)


class Optional(Generic[T]):
    """Indicates an optional field."""

    def __init__(self, field_type: T):
        self.field_type = field_type

    @classmethod
    def __class_getitem__(cls, item):
        return cls(item)


class AutoIncrement:
    """AutoIncrement field, usually for primary keys."""

    def __init__(self):
        self.field_type = int

    @classmethod
    def __class_getitem__(cls, item):
        return cls()


class PrimaryKey:
    """Primary Key field."""

    def __init__(
        self, field_type: T, auto_increment: bool = False, compound: bool = False
    ):
        self.field_type = field_type
        self.auto_increment = auto_increment
        self.compound = compound

    @classmethod
    def __class_getitem__(cls, item):
        return cls(item)


class Index:
    """Defines an index on one or more fields."""

    def __init__(self, *fields, unique: bool = False, index_type: str = "btree"):
        self.fields = fields
        self.unique = unique
        self.index_type = index_type

    @classmethod
    def __class_getitem__(cls, *items):
        return cls(*items)


class CompoundPrimaryKey:
    """Defines a compound primary key."""

    def __init__(self, *fields):
        self.fields = fields

    @classmethod
    def __class_getitem__(cls, *items):
        return cls(*items)


class HasMany(Generic[T]):
    """Defines a one-to-many relationship."""

    def __init__(self, related_model: T):
        self.related_model = related_model
        self.field_type = None

    @classmethod
    def __class_getitem__(cls, item):
        return cls(item)


class HasOne(Generic[T]):
    """Defines a one-to-one (or many-to-one) relationship."""

    def __init__(self, related_model: T):
        self.related_model = related_model
        self.field_type = int

    @classmethod
    def __class_getitem__(cls, item):
        return cls(item)

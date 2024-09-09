from typing import Generic, TypeVar

T = TypeVar("T")


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

    def __init__(self, field_type: T):
        self.field_type = field_type

    @classmethod
    def __class_getitem__(cls, item):
        return cls(item)


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

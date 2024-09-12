from typing import Any, Dict, get_type_hints

from zara.errors import DuplicateResourceError, ResourceNotFoundError

from .fields import DatabaseField, HasMany

DEFAULTS = {}
PRIVATES = {}


class Model:
    _table_name: str
    _fields: Dict[str, Any]

    def __init__(self, **kwargs):
        self._defaults: Dict[str, Any]
        self._values = kwargs
        self.changed_fields = []
        for key, value in self._get_fields().items():
            if key in self._values:
                continue
            if self.__class__.__name__ in DEFAULTS:
                if key in DEFAULTS[self.__class__.__name__]:
                    self._values[key] = DEFAULTS[self.__class__.__name__][
                        key
                    ].get_value()
        for key, value in kwargs.items():
            self._values[key] = value

    @classmethod
    def _get_fields(cls):
        """Get model fields dynamically from class annotations."""
        fields = {
            k: v for k, v in cls.__annotations__.items() if not isinstance(v, HasMany)
        }
        print(fields)
        for base in cls.mro():
            if base is not object:
                annotations = get_type_hints(base)
                print(annotations)
                for key, value in annotations.items():
                    if (
                        not key.startswith("_")
                        and not callable(value)
                        and key not in fields
                        and not isinstance(value, HasMany)
                    ):
                        if isinstance(getattr(base, key), DatabaseField):
                            if getattr(base, key).default is not None:
                                if cls.__name__ not in DEFAULTS:
                                    DEFAULTS[cls.__name__] = {}
                                DEFAULTS[cls.__name__][key] = getattr(base, key)
                            if getattr(base, key).private:
                                if cls.__name__ not in PRIVATES:
                                    PRIVATES[cls.__name__] = {}
                                PRIVATES[cls.__name__][key] = getattr(base, key)
                            fields[key] = getattr(base, key)
                        else:
                            fields[key] = value
        return fields

    @classmethod
    def _columns(cls):
        return (k for k in cls.__annotations__.keys() if not isinstance(k, HasMany))

    @classmethod
    def _get_table_name(cls):
        """Get the table name from the class name."""
        return cls.__name__.lower()

    async def create(self, db):
        """Insert a new record in the database using the provided db context."""
        fields = self._get_fields()
        columns = ", ".join(field for field in fields.keys() if field != "id")
        placeholders = ", ".join([f"${i+1}" for i in range(len(fields) - 1)])
        values = tuple(
            self._values.get(field) for field in fields.keys() if field != "id"
        )
        query = f"INSERT INTO {self._get_table_name()} ({columns}) VALUES ({placeholders}) RETURNING id;"

        try:
            result = await self._execute(db, query, values)
        except Exception as e:
            if "duplicate key value violates unique constraint" in str(e):
                raise DuplicateResourceError(f"Duplicate resource found: {self}")
            raise e
        if db.backend == "postgresql":
            self._values["id"] = result[0]["id"]
        else:
            self._values["id"] = result[0][0]

        return self

    async def save(self, db):
        """Update an existing record in the database."""
        if not self.changed_fields:
            return

        changed_fields = {key: self._values[key] for key in self.changed_fields}

        updates = ", ".join(
            [f"{key} = ${i+1}" for i, key in enumerate(changed_fields.keys(), start=0)]
        )
        values = tuple(changed_fields.values())

        query = f"UPDATE {self._get_table_name()} SET {updates} WHERE id = ${len(changed_fields) + 1};"

        await self._execute(db, query, values + (self._values["id"],))

        self.changed_fields.clear()

    @classmethod
    async def get(cls, db, **kwargs):
        """Retrieve a record from the database."""
        table_name = cls._get_table_name()
        where_clause = " AND ".join(
            [f"{key} = ${i+1}" for i, key in enumerate(kwargs.keys())]
        )
        values = tuple(kwargs.values())

        query = f"SELECT * FROM {table_name} WHERE {where_clause} LIMIT 1;"
        result = await cls._execute(db, query, values)
        if result:
            if db.backend == "postgresql":
                return cls(**result[0])
            return cls(**dict(zip(cls._columns(), result[0])))
        filters = {f"{k}={v}" for k, v in kwargs.items()}
        raise ResourceNotFoundError(
            f"Result not found for criteria: {' '.join(filters)}"
        )

    @classmethod
    async def get_or_create(cls, db, **kwargs):
        """Get a record if it exists, otherwise create it."""
        instance = await cls.get(db, **kwargs)
        if instance:
            return instance, False
        return await cls(**kwargs).create(db), True

    @classmethod
    async def _execute(cls, db, query, values):
        """Helper method to execute a query using the provided db context."""
        if db.backend == "sqlite":
            async with db.connection.execute(query, values) as cursor:
                return await cursor.fetchall()
        elif db.backend == "postgresql":
            return await db.connection.fetch(query, *values)

    def __repr__(self):
        """String representation of the model."""
        return f"<{self.__class__.__name__}: {self.as_dict()}>"

    def __getattribute__(self, name):
        _values = object.__getattribute__(self, "_values")
        if name in _values:
            return _values[name]
        return object.__getattribute__(self, name)

    def as_dict(self):
        return {
            k: v
            for k, v in self._values.items()
            if k not in PRIVATES[self.__class__.__name__]
        }

    def set(self, **kwargs):
        if not hasattr(self, "changed_fields"):
            object.__setattr__(self, "changed_fields", [])
        for name, value in kwargs.items():
            if "_values" in self.__dict__ and name in self._get_fields():
                self._values[name] = value
                # Add the field to changed_fields if not already tracked
                if name not in self.changed_fields:
                    self.changed_fields.append(name)

from typing import Any, Dict, get_type_hints

from zara.application.events import Event
from zara.errors import DuplicateResourceError, ResourceNotFoundError
from zara.utilities.context import Context

from .fields import DatabaseField, HasMany

DEFAULTS = {}
PRIVATES = {}


# generic class with __dict__ method
class ModelWithDict:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    @property
    def __dict__(self):
        return self.kwargs


class Model:
    _table_name: str
    _fields: Dict[str, Any]

    def __init__(self, should_audit=True, **kwargs):
        self._defaults: Dict[str, Any]
        self._values = kwargs
        self.changed_fields = []
        self.should_audit = should_audit
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
        self.public = self._check_if_public()

    @classmethod
    def _check_if_public(cls):
        for base in cls.mro():
            if base is not object:
                if issubclass(base, Public):
                    return True
        return False

    @classmethod
    def _get_fields(cls):
        """Get model fields dynamically from class annotations."""
        fields = {
            k: v for k, v in cls.__annotations__.items() if not isinstance(v, HasMany)
        }
        for base in cls.mro():
            if base is not object:
                annotations = get_type_hints(base)
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
        if cls._check_if_public():
            return f"public.{cls.__name__.lower()}"
        return cls.__name__.lower()

    @staticmethod
    def _get_public_table_name_for_querying(table_name):
        if table_name.startswith("public."):
            table_name = table_name.replace("public.", "")
        if table_name.startswith("public"):
            table_name = table_name[6:]
        return table_name

    async def create(self, public=False):
        """Insert a new record in the database using the provided db context."""
        db = Context.get_db()
        request = Context.get_request()
        fields = self._get_fields()
        columns = ", ".join(field for field in fields.keys())
        placeholders = ", ".join([f"${i+1}" for i in range(len(fields))])
        values = tuple(self._values.get(field) or None for field in fields.keys())
        table_name = self._get_table_name()
        # if all the values are none
        has_values = [v for v in values if v is not None]
        if has_values:
            if public:
                table_name = self._get_public_table_name_for_querying(table_name)
                query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders}) RETURNING *;"
            else:
                query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders}) RETURNING id;"
        else:
            # Insert with default values
            if public:
                table_name = self._get_public_table_name_for_querying(table_name)
                query = f"INSERT INTO {table_name} DEFAULT VALUES RETURNING *;"
            else:
                query = f"INSERT INTO {table_name} DEFAULT VALUES RETURNING id;"

        try:
            result = await self._execute(
                db, query, values if has_values else [], public=public
            )
        except Exception as e:
            if "duplicate key value violates unique constraint" in str(e):
                raise DuplicateResourceError(f"Duplicate resource found: {self}")
            raise e

        if not has_values:
            self._values.update(result[0])
        else:
            self._values["id"] = result[0]["id"]

        if self.should_audit and not public:
            event_bus = Context.get_event_bus()
            if event_bus is not None:
                event_bus.dispatch_event(
                    Event(
                        "AuditEvent",
                        {
                            "model": self,
                            "request": request,
                            "meta": ModelWithDict(
                                action_type="create",
                                object_type=self.__class__.__name__,
                                customer=Context.get_customer(),
                            ),
                        },
                    )
                )
        return self

    async def save(self):
        """Update an existing record in the database."""
        request = Context.get_request()
        request.logger.info(f"changed fields: {self.changed_fields}")
        if not self.changed_fields:
            return

        changed_fields = {key: self._values[key] for key in self.changed_fields}

        updates = ", ".join(
            [f"{key} = ${i+1}" for i, key in enumerate(changed_fields.keys(), start=0)]
        )
        values = tuple(changed_fields.values())

        query = f"UPDATE {self._get_table_name()} SET {updates} WHERE id = ${len(changed_fields) + 1};"

        db = Context.get_db()
        await self._execute(db, query, values + (self._values["id"],))

        self.changed_fields.clear()

        if self.should_audit:
            event_bus = Context.get_event_bus()
            if event_bus is not None:
                event_bus.dispatch_event(
                    Event(
                        "AuditEvent",
                        {
                            "model": self,
                            "request": request,
                            "meta": ModelWithDict(
                                action_type="update",
                                object_type=self.__class__.__name__,
                                customer=Context.get_customer(),
                            ),
                        },
                    )
                )

    @classmethod
    async def get(cls, **kwargs):
        """Retrieve a record from the database."""
        table_name = cls._get_table_name()
        is_public = cls._check_if_public()
        where_clause = " AND ".join(
            [f"{key} = ${i+1}" for i, key in enumerate(kwargs.keys())]
        )
        values = tuple(kwargs.values())

        query = f"SELECT * FROM {table_name if not is_public else table_name.replace('public.', '')} WHERE {where_clause} LIMIT 1;"
        db = Context.get_db()
        result = await cls._execute(db, query, values, public=is_public)
        if result:
            return cls(**result[0])
        filters = {f"{k}={v}" for k, v in kwargs.items()}
        raise ResourceNotFoundError(
            f"Result not found for criteria: {' '.join(filters)}"
        )

    @classmethod
    async def first(cls, logger, throws=True):
        """Retrieve the first record."""
        db = Context.get_db()
        if not cls._check_if_public():
            logger.error("running in private")
            result = await cls._execute(
                db, "SELECT * FROM {} LIMIT 1;".format(cls._get_table_name()), []
            )
        else:
            tbl = cls._get_public_table_name_for_querying(cls._get_table_name())
            logger.error(f"tbl: {tbl}")
            result = await cls._execute(
                db,
                "SELECT * FROM public.{} LIMIT 1;".format(tbl),
                [],
                public=True,
            )

        logger.error(f"result: {result}")
        if result and str(result) != "SELECT 0":
            return cls(**result[0])
        if throws:
            raise ResourceNotFoundError("Result not found.")
        return None

    @classmethod
    async def first_or_create(cls, logger, **kwargs):
        """Retrieve the first record or create it."""
        logger.error("running get first")
        instance = await cls.first(logger, throws=False)
        if instance:
            logger.error(f"got instance: {instance}")
            return instance, False
        logger.error(f"running create since we didnt find it: {kwargs}")
        new_cls = cls(**kwargs)
        if new_cls._check_if_public():
            logger.error(f"the values: {new_cls._values}")
            return await new_cls.create(public=True), True
        return await new_cls.create(), True

    @classmethod
    async def get_or_create(cls, db, **kwargs):
        """Get a record if it exists, otherwise create it."""
        instance = await cls.get(db, **kwargs)
        if instance:
            return instance, False
        return await cls(**kwargs).create(db), True

    @classmethod
    async def _execute(cls, db, query, values, public=False):
        """Helper method to execute a query using the provided db context."""
        if public is True:
            if values:
                return await db.execute_in_public(query, *values)
            return await db.execute_in_public(query)
        if values:
            return await db.connection.fetch(query, *values)
        return await db.connection.fetch(query)

    def __repr__(self):
        """String representation of the model."""
        return f"<{self.__class__.__name__}: {self.as_dict()}>"

    def __getattribute__(self, name):
        _values = object.__getattribute__(self, "_values")
        if name in _values:
            return _values[name]
        return object.__getattribute__(self, name)

    def as_dict(self, include_private=False):
        if include_private is True:
            return {k: v for k, v in self._values.items()}
        return {
            k: v
            for k, v in self._values.items()
            if k not in PRIVATES.get(self.__class__.__name__, [])
        }

    @property
    def __dict__(self):
        return self.as_dict()

    def as_dictionary(self):
        return self.as_dict()

    def to_dict(self):
        return self.as_dict()

    def dict(self):
        return self.as_dict()

    def set(self, **kwargs):
        if not hasattr(self, "changed_fields"):
            object.__setattr__(self, "changed_fields", [])
        for name, value in kwargs.items():
            if hasattr(self, "_values") and name in self._get_fields():
                self._values[name] = value
                # Add the field to changed_fields if not already tracked
                if name not in self.changed_fields:
                    self.changed_fields.append(name)


class Public:
    pass

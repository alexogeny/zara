import sqlite3
from typing import Optional, Type

import asyncpg


class ORMBase:
    _db_connection = None
    _db_type = None

    def __init__(self, **kwargs):
        for field_name, field_type in self.__annotations__.items():
            setattr(self, field_name, kwargs.get(field_name))

    @classmethod
    async def setup(cls, db_url: str):
        if "sqlite" in db_url:
            cls._db_connection = sqlite3.connect(db_url.split(":///")[1])
            cls._db_type = "sqlite"
        elif "asyncpg" in db_url:
            cls._db_connection = await asyncpg.create_pool(db_url)
            cls._db_type = "asyncpg"

    @classmethod
    async def get_connection(cls):
        if cls._db_type == "sqlite":
            return cls._db_connection
        elif cls._db_type == "asyncpg":
            return await cls._db_connection.acquire()

    @classmethod
    async def release_connection(cls, conn):
        if cls._db_type == "asyncpg":
            await cls._db_connection.release(conn)

    @classmethod
    async def create_table(cls):
        conn = await cls.get_connection()
        table_name = cls._table_name
        fields = ", ".join(
            [
                f"{name} {cls._field_type(field)}"
                for name, field in cls.__annotations__.items()
            ]
        )
        query = f"CREATE TABLE IF NOT EXISTS {table_name} ({fields})"

        if cls._db_type == "sqlite":
            conn.execute(query)
        else:
            await conn.execute(query)

    @classmethod
    async def clean_up_tables(cls):
        conn = await cls.get_connection()
        query = f"DELETE FROM {cls._table_name}"
        if cls._db_type == "sqlite":
            conn.execute(query)
        else:
            await conn.execute(query)

    @classmethod
    def _field_type(cls, field: Type) -> str:
        if issubclass(field, AutoIncrementInt):
            return "INTEGER PRIMARY KEY AUTOINCREMENT"
        if field is int:
            return "INTEGER"
        if field is str:
            return "TEXT"
        if field == Optional[int]:
            return "INTEGER"
        return "TEXT"

    async def save(self):
        conn = await self.__class__.get_connection()
        fields = []
        values = []

        for name, field_type in self.__annotations__.items():
            value = getattr(self, name, None)
            if (
                not isinstance(field_type, type)
                or not issubclass(field_type, AutoIncrementInt)
                or value is not None
            ):
                fields.append(name)
                values.append(f"'{value}'" if isinstance(value, str) else str(value))

        fields_str = ", ".join(fields)
        values_str = ", ".join(values)
        query = f"INSERT INTO {self.__class__._table_name} ({fields_str}) VALUES ({values_str})"

        if self.__class__._db_type == "sqlite":
            conn.execute(query)
        else:
            await conn.execute(query)

        if isinstance(self.__annotations__.get("id"), AutoIncrementInt):
            if self.__class__._db_type == "sqlite":
                self.id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            else:
                self.id = await conn.fetchval("SELECT lastval()")

    async def update(self):
        conn = await self.__class__.get_connection()
        fields = ", ".join(
            [f"{name}='{getattr(self, name)}'" for name in self.__annotations__.keys()]
        )
        query = f"UPDATE {self.__class__._table_name} SET {fields} WHERE id = {self.id}"

        if self.__class__._db_type == "sqlite":
            conn.execute(query)
        else:
            await conn.execute(query)

    @classmethod
    async def get(cls, **filters):
        conn = await cls.get_connection()

        where_clause = " AND ".join([f"{key} = ?" for key in filters.keys()])
        query = f"SELECT * FROM {cls._table_name} WHERE {where_clause}"

        values = tuple(filters.values())

        if cls._db_type == "sqlite":
            cursor = conn.execute(query, values)
            row = cursor.fetchone()
        else:
            row = await conn.fetchrow(query, *values)

        return row

    @classmethod
    async def all(cls):
        conn = await cls.get_connection()
        query = f"SELECT * FROM {cls._table_name}"

        if cls._db_type == "sqlite":
            cursor = conn.execute(query)
            rows = cursor.fetchall()
        else:
            rows = await conn.fetch(query)

        return rows


class AutoIncrementInt:
    pass


class related:
    def __init__(self, model_name: str):
        self.model_name = model_name

import sqlite3
from datetime import datetime, timezone
from typing import Optional, Type

import asyncpg


class ORMBase:
    _db_connection = None
    _db_type = None
    _is_partitioned_by_day = False

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
    def _get_table_name(cls, date: datetime | None = None) -> str:
        table_name = cls._table_name
        if cls._is_partitioned_by_day:
            if date is None:
                date = datetime.now(tz=timezone.utc)
            table_name = f"{table_name}_{date.strftime('%Y_%m_%d')}"
        return table_name

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
    async def create_table(cls, date: datetime = None):
        conn = await cls.get_connection()
        table_name = cls._get_table_name(date)
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

    async def save(self, date: datetime = None):
        cls = self.__class__
        await cls.create_table(date)  # Ensure the table exists
        conn = await cls.get_connection()
        table_name = cls._get_table_name(date)

        fields = []
        values = []

        for name, field_type in cls.__annotations__.items():
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
        query = f"INSERT INTO {table_name} ({fields_str}) VALUES ({values_str})"

        if cls._db_type == "sqlite":
            conn.execute(query)
        else:
            await conn.execute(query)

        if isinstance(cls.__annotations__.get("id"), AutoIncrementInt):
            if cls._db_type == "sqlite":
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
    async def get(cls, date: datetime = None, **filters):
        conn = await cls.get_connection()
        table_name = cls._get_table_name(date)

        where_clause = " AND ".join([f"{key} = ?" for key in filters.keys()])
        query = f"SELECT * FROM {table_name} WHERE {where_clause}"

        values = tuple(filters.values())

        if cls._db_type == "sqlite":
            try:
                cursor = conn.execute(query, values)
                row = cursor.fetchone()
            except sqlite3.OperationalError:  # Handle case where table doesn't exist
                return None
        else:
            row = await conn.fetchrow(query, *values)

        return row

    @classmethod
    async def all(cls):
        conn = await cls.get_connection()

        if cls._is_partitioned_by_day:
            query = "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?"
            table_pattern = f"{cls._table_name}_%"

            if cls._db_type == "sqlite":
                cursor = conn.execute(query, (table_pattern,))
                tables = [row[0] for row in cursor.fetchall()]
            else:
                tables = await conn.fetch(query, table_pattern)

            latest_table = max(tables) if tables else None
            if latest_table:
                query = f"SELECT * FROM {latest_table}"
                if cls._db_type == "sqlite":
                    cursor = conn.execute(query)
                    rows = cursor.fetchall()
                else:
                    rows = await conn.fetch(query)
            else:
                rows = []
        else:
            query = f"SELECT * FROM {cls._table_name}"
            if cls._db_type == "sqlite":
                cursor = conn.execute(query)
                rows = cursor.fetchall()
            else:
                rows = await conn.fetch(query)
            tables = [cls._table_name]

        if not cls._is_partitioned_by_day:
            return rows

        return rows, tables


class AutoIncrementInt:
    pass


class related:
    def __init__(self, model_name: str):
        self.model_name = model_name

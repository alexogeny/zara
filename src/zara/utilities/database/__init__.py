import aiosqlite
import asyncpg

from zara.utilities.database.migrations import MigrationManager
from zara.utilities.dotenv import env


class AsyncDatabase:
    def __init__(self, db_name: str, backend: str = "sqlite"):
        self.db_name = db_name
        self.backend = backend
        self.connection = None
        self.db_url = env.get(
            "DATABASE_URL", default="postgresql://user:password@localhost/dbname"
        )
        if "postgresql" in self.db_url:
            self.backend = "postgresql"

    async def connect(self):
        """Establish the connection to the database."""
        if self.backend == "sqlite":
            self.connection = await aiosqlite.connect(f"{self.db_name}.db")
            await self._ensure_sqlite_file_exists()
        elif self.backend == "postgresql":
            self.connection = await asyncpg.connect(self.db_url)
            await self._ensure_schema_exists()
            await self.connection.execute(f"SET search_path TO {self.db_name};")
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")
        await MigrationManager().apply_pending_migrations(self)

    async def _create_psql_public_databases(self):
        await self.connection.execute(
            "CREATE TABLE IF NOT EXISTS public.databases (schema_name TEXT PRIMARY KEY);"
        )

    async def _ensure_schema_exists(self):
        """Ensures that the schema exists in PostgreSQL, and if not, creates it."""
        result = await self.connection.fetchval(
            f"SELECT schema_name FROM information_schema.schemata WHERE schema_name = '{self.db_name}'"
        )
        if not result:
            await self.connection.execute(
                f"CREATE SCHEMA IF NOT EXISTS {self.db_name};"
            )
            await self._create_psql_public_databases()
            await self.connection.execute(
                "INSERT INTO public.databases (schema_name) VALUES ($1)", self.db_name
            )

    async def _ensure_sqlite_file_exists(self):
        """Ensures that the SQLite file exists and registers it."""
        async with aiosqlite.connect("public_registry.db") as conn:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS databases (name TEXT PRIMARY KEY);"
            )
            await conn.execute(
                "INSERT OR IGNORE INTO databases (name) VALUES (?);", (self.db_name,)
            )
            await conn.commit()

    async def disconnect(self):
        """Close the database connection."""
        if self.connection:
            if self.backend == "sqlite":
                await self.connection.commit()
            await self.connection.close()

    # Implement the asynchronous context manager protocol
    async def __aenter__(self):
        """Enter the async context manager by connecting to the database."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit the async context manager by disconnecting from the database."""
        await self.disconnect()

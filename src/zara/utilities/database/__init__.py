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
        self.connection = await asyncpg.connect(self.db_url)
        await self._ensure_schema_exists()
        await self.connection.execute(f"SET search_path TO {self.db_name};")
        await MigrationManager().apply_pending_migrations(self)

    async def _create_psql_public_databases(self):
        await self.connection.execute(
            "CREATE TABLE IF NOT EXISTS public.databases (schema_name TEXT PRIMARY KEY);"
        )

    async def execute_in_public(self, statement, *values):
        """Execute a statement in the public schema or database."""
        await self.connection.execute("SET search_path TO public;")
        try:
            if values:
                result = await self.connection.execute(statement, *values)
            else:
                result = await self.connection.execute(statement)
        finally:
            await self.connection.execute(f"SET search_path TO {self.db_name};")
        return result

    async def fetch_in_public(self, statement, *values):
        """Execute a statement in the public schema or database."""
        await self.connection.execute("SET search_path TO public;")
        try:
            if values:
                result = await self.connection.fetch(statement, *values)
            else:
                result = await self.connection.fetch(statement)
        finally:
            await self.connection.execute(f"SET search_path TO {self.db_name};")
        return result

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

    async def disconnect(self):
        """Close the database connection."""
        if self.connection:
            await self.connection.close()

    # Implement the asynchronous context manager protocol
    async def __aenter__(self):
        """Enter the async context manager by connecting to the database."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit the async context manager by disconnecting from the database."""
        await self.disconnect()

from contextlib import asynccontextmanager

from zara.database.base import ORMBase


class session:
    def __init__(self):
        self._connection = None
        self._transaction = None

    async def __aenter__(self):
        self._connection = await ORMBase.get_connection()

        if ORMBase._db_type == "asyncpg":
            self._transaction = self._connection.transaction()
            await self._transaction.start()

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if ORMBase._db_type == "asyncpg":
            if exc_type is None:
                await self._transaction.commit()
            else:
                await self._transaction.rollback()

        if ORMBase._db_type == "asyncpg":
            await ORMBase.release_connection(self._connection)

        self._connection = None
        self._transaction = None

    @asynccontextmanager
    async def manage_session(self):
        async with self:
            yield

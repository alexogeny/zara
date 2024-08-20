import asyncio
import unittest

from zara.database.base import AutoIncrementInt, ORMBase, related
from zara.database.session import session


class TestORM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        asyncio.run(ORMBase.setup("sqlite:///:memory:"))
        asyncio.run(TestPerson.create_table())
        asyncio.run(TestPet.create_table())

    def setUp(self):
        asyncio.run(TestPerson.clean_up_tables())
        asyncio.run(TestPet.clean_up_tables())

    async def save_entity(self, entity):
        async with session():
            await entity.save()

    def test_create_person(self):
        person = TestPerson(name="Test Hermione")
        asyncio.run(self.save_entity(person))

        saved_person = asyncio.run(self.get_person_by_name("Test Hermione"))
        self.assertIsNotNone(saved_person, "Person should be saved and retrievable")
        self.assertEqual(saved_person[0], 1)
        self.assertEqual(saved_person[1], "Test Hermione")

    async def get_person_by_name(self, name):
        query = "SELECT * FROM test_person WHERE name = ?"
        conn = await ORMBase.get_connection()
        if ORMBase._db_type == "asyncpg":
            row = await conn.fetchrow(query, name)
        else:
            cursor = conn.execute(query, (name,))
            row = cursor.fetchone()
        return row


class TestPerson(ORMBase):
    _table_name = "test_person"
    id: AutoIncrementInt
    name: str


class TestPet(ORMBase):
    _table_name = "test_pet"
    id: AutoIncrementInt
    name: str
    age: int
    owner: TestPerson = related("TestPerson")

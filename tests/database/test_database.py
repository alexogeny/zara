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

        saved_person = asyncio.run(TestPerson.get(name="Test Hermione"))
        self.assertIsNotNone(saved_person, "Person should be saved and retrievable")
        self.assertEqual(saved_person[0], 1)
        self.assertEqual(saved_person[1], "Test Hermione")

    def test_get_all_peeople(self):
        person = TestPerson(name="Test Hermione")
        person_two = TestPerson(name="Test Ronaldo")
        asyncio.run(self.save_entity(person))
        asyncio.run(self.save_entity(person_two))
        saved_people = asyncio.run(TestPerson.all())
        self.assertIsNotNone(saved_people, "People should be saved and retrievable")
        names = [p[1] for p in saved_people]
        self.assertEqual(sorted(names), ["Test Hermione", "Test Ronaldo"])


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

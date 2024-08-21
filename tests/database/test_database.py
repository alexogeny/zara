import asyncio
import unittest
from datetime import datetime, timedelta, timezone

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

    async def save_entity(self, entity, date=None):
        async with session():
            await entity.save(date=date)

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

    def test_create_partitioned_model(self):
        al_today = TestAuditLog(action_text="I did a thing today")
        asyncio.run(self.save_entity(al_today))

        saved_al_today = asyncio.run(TestAuditLog.get(id=1))
        self.assertIsNotNone(saved_al_today, "Audit log should be saved + gettable")
        self.assertEqual(saved_al_today[1], "I did a thing today")

        yesterday = datetime.now(tz=timezone.utc) - timedelta(days=1)
        al_yesterday = TestAuditLog(action_text="I did a thing yesterday")
        asyncio.run(self.save_entity(al_yesterday, date=yesterday))

        saved_al_yesterday = asyncio.run(TestAuditLog.get(id=1, date=yesterday))
        self.assertIsNotNone(
            saved_al_yesterday, "Audit log from yesterday should be saved + gettable"
        )
        self.assertEqual(saved_al_yesterday[1], "I did a thing yesterday")

        saved_al_today_again = asyncio.run(TestAuditLog.get(id=1))
        self.assertIsNotNone(
            saved_al_today_again, "Today's audit log should still be gettable"
        )
        self.assertEqual(saved_al_today_again[1], "I did a thing today")


class TestPerson(ORMBase):
    _table_name = "test_person"
    id: AutoIncrementInt
    name: str


class TestAuditLog(ORMBase):
    _table_name = "test_audit_log"
    _is_partitioned_by_day = True

    id: AutoIncrementInt
    action_text: str


class TestPet(ORMBase):
    _table_name = "test_pet"
    id: AutoIncrementInt
    name: str
    age: int
    owner: TestPerson = related("TestPerson")

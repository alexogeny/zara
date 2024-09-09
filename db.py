# Mixins
import asyncio

from example_models import Pet, User
from zara.utilities.database import AsyncDatabase


async def main():
    database = AsyncDatabase
    async with database("acme_corp", backend="sqlite") as db:
        user = await User(name="John Smith").create(db)

        pet = await Pet(name="Kitty", owner=user.id).create(db)
        print(f"Pet created: {pet}")
        retrieved_user = await User.get(db, name="John Smith")
        assert retrieved_user.name == "John Smith"
        print(f"User created and then retrieved: {user}")

        user, created = await User.get_or_create(db, name="Jane Doe")
        print(f"User {'created' if created else 'retrieved'}: {user}")

        user.set(name="Jane Smith")
        print(f"Modified user: {user}")
        await user.save(db)


asyncio.run(main())

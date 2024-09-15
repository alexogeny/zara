import time
import uuid

# Define the Base57 alphabet
BASE57_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def base57_encode(num):
    """Convert an integer to a Base57 string."""
    if num == 0:
        return BASE57_ALPHABET[0]

    base57 = ""
    base = len(BASE57_ALPHABET)
    while num > 0:
        num, rem = divmod(num, base)
        base57 = BASE57_ALPHABET[rem] + base57
    return base57


def uuid_to_base57(uuid_obj):
    """Convert a UUID to a Base57 encoded string."""
    # Convert the UUID to a 128-bit integer
    uuid_int = uuid_obj.int
    # Encode the integer to a Base57 string
    return base57_encode(uuid_int)


def generate_lexicographical_uuid():
    # Get the current time in milliseconds
    timestamp = int(time.time() * 1000)

    # Convert the timestamp to a Base57 string
    timestamp_base57 = base57_encode(timestamp)

    # Generate a UUID
    new_uuid = uuid.uuid4()

    # Convert the UUID to a Base57 string
    uuid_base57 = uuid_to_base57(new_uuid)

    # Combine the timestamp and the base57 UUID
    lexicographical_id = f"{timestamp_base57}{uuid_base57}"

    return lexicographical_id

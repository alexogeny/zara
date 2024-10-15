from datetime import datetime, timezone


def now(naive: bool = False):
    dt = datetime.now(tz=timezone.utc)
    if not naive:
        return dt
    return dt.replace(tzinfo=None)


def naive_now():
    return now(naive=True)

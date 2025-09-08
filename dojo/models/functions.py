import pytz
from ulid import ULID
from datetime import datetime, UTC

__all__ = [
  'generate_ulid',
  'generate_utcnow',
]

def generate_ulid():
  return str(ULID())

def generate_utcnow():
  return datetime.now(pytz.utc)

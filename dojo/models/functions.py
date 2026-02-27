import pytz
from ulid import ULID
from datetime import datetime, UTC

__all__ = [
  'generate_ulid',
  'generate_utcnow',
]

def generate_ulid():
  """Return a new ULID as 16-byte binary (big-endian)."""
  return ULID().bytes

def generate_utcnow():
  return datetime.now(pytz.utc)

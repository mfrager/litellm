from sqlalchemy import DateTime, Column

from .functions import generate_utcnow

class CommonBase():
  ts_created = Column(DateTime, default=generate_utcnow, nullable=False)
  ts_updated = Column(DateTime, default=generate_utcnow, onupdate=generate_utcnow, nullable=False)

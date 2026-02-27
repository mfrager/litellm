from sqlalchemy import LargeBinary
from sqlalchemy.dialects.mysql import VARBINARY
from sqlalchemy.orm import declarative_base

# 16-byte binary ULID: VARBINARY(16) on MySQL, BLOB/LargeBinary elsewhere
ULID_BINARY = LargeBinary(16).with_variant(VARBINARY(16), 'mysql')

Base = declarative_base()

#!/usr/bin/env python3
"""
Migrates existing SQLite data from nyayasetu.db to PostgreSQL using SQLAlchemy ORM.
Handles boolean type conversion, foreign keys, and idempotent inserts.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from models.database import (
    Base, User, Workflow, Task, ComplianceAlert,
    Correction, SearchCache, Act, Provision, StatuteMapping, IngestionLog,
    VerificationReport, DATABASE_URL
)

SQLITE_PATH = os.path.join(os.path.dirname(__file__), "..", "nyayasetu.db")
if not os.path.exists(SQLITE_PATH):
    print("No local nyayasetu.db found, skipping data migration.")
    sys.exit(0)

sqlite_engine = create_engine(f"sqlite:///{SQLITE_PATH}", connect_args={"check_same_thread": False})
SqliteSession = sessionmaker(bind=sqlite_engine)

pg_url = DATABASE_URL
if pg_url.startswith("postgres://"):
    pg_url = pg_url.replace("postgres://", "postgresql://", 1)

pg_engine = create_engine(pg_url)
PgSession = sessionmaker(bind=pg_engine)

sqlite_db = SqliteSession()
pg_db = PgSession()

MODELS = [
    User,
    Act,
    Provision,
    StatuteMapping,
    Correction,
    SearchCache,
    IngestionLog,
    Workflow,
    Task,
    ComplianceAlert,
    VerificationReport,
]

print(f"Migrating records from {SQLITE_PATH} to PostgreSQL...")

for model in MODELS:
    table_name = model.__tablename__
    try:
        sqlite_records = sqlite_db.query(model).all()
        count = len(sqlite_records)
        if count == 0:
            continue
        print(f"Processing {table_name}: found {count} rows in SQLite...")
        
        migrated = 0
        for record in sqlite_records:
            # Check if record already exists in Postgres by PK
            pk_val = getattr(record, "id", None)
            if pk_val:
                exists = pg_db.query(model).filter(model.id == pk_val).first()
                if exists:
                    continue
            
            # Detach from sqlite session and add to pg
            sqlite_db.expunge(record)
            # Ensure boolean fields are boolean
            for col in model.__table__.columns:
                if str(col.type).lower().startswith("bool"):
                    val = getattr(record, col.name, None)
                    if isinstance(val, int):
                        setattr(record, col.name, bool(val))
            
            pg_db.merge(record)
            migrated += 1
        
        pg_db.commit()
        print(f"  ✓ {table_name}: successfully synced {migrated} new rows.")
    except Exception as e:
        pg_db.rollback()
        print(f"  ✗ {table_name} migration note: {e}")

print("\n--- Current row counts in PostgreSQL ---")
for model in MODELS:
    try:
        cnt = pg_db.query(model).count()
        print(f"  {model.__tablename__}: {cnt}")
    except Exception as e:
        print(f"  {model.__tablename__}: error ({e})")

sqlite_db.close()
pg_db.close()
print("PostgreSQL migration complete!")

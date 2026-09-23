import os
import uuid
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, String, DateTime,
    Boolean, Text, Integer, ForeignKey
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nyayasetu.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")  # user, advocate, intern, admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    company_a = Column(String, nullable=True)
    company_b = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String, default="active")  # active, completed, archived
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    document_type = Column(String, nullable=True)
    is_completed = Column(Boolean, default=False)
    is_required = Column(Boolean, default=True)
    order_index = Column(Integer, default=0)
    due_date = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ComplianceAlert(Base):
    __tablename__ = "compliance_alerts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    law_area = Column(String, nullable=False)  # labour, data_privacy, corporate, etc.
    severity = Column(String, default="info")  # info, warning, critical
    source_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    query_type = Column(String, nullable=False)  # case_search, draft, legal_aid, compliance
    encrypted_query = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Correction(Base):
    """Correction Memory (harness-sprint Part A): a deterministic, auditable log of
    human-flagged verdict corrections, checked BEFORE the normal verification
    pipeline runs. Direction is NOT symmetric -- see services/correction_memory.py
    for why 'tighten' (toward Mismatch/Not-found) takes effect immediately while
    'loosen' (toward Verified) requires explicit admin confirmation first."""
    __tablename__ = "corrections"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    trigger_type = Column(String, nullable=False)  # citation_verdict | case_resolution
    input_signature = Column(String, nullable=False, index=True)  # normalized case_name + citation_string, exact-match only
    system_output = Column(String, nullable=False)
    correct_output = Column(String, nullable=False)
    direction = Column(String, nullable=False)  # tighten | loosen
    status = Column(String, default="pending_review", index=True)  # confirmed | pending_review | rejected
    flagged_by = Column(String, ForeignKey("users.id"), nullable=False)
    flagged_at = Column(DateTime, default=datetime.utcnow)
    note = Column(Text, nullable=True)
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)


class SearchCache(Base):
    __tablename__ = "search_cache"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    query_hash = Column(String(64), unique=True, nullable=False, index=True)
    query_text = Column(Text, nullable=False)
    results_json = Column(Text, nullable=False)
    source = Column(String(50), nullable=False)  # ik_api | ik_scrape | commonlii
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

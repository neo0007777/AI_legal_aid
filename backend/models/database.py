import os
import uuid
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, String, DateTime,
    Boolean, Text, Integer, ForeignKey, Float, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nyayasetu.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_recycle=300
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
    preferred_language = Column(String, default="en")  # app-wide language switcher, see LanguageContext.jsx


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


class UserSession(Base):
    """Loophole fix #2: auth was pure stateless JWT with no way to revoke a
    token before its natural expiry -- /logout did nothing server-side. Every
    issued access token now gets a row here (id = the token's jti claim), so
    logout, admin-forced logout, and "log out of all devices" all become a
    single UPDATE rather than being architecturally impossible."""
    __tablename__ = "user_sessions"

    id = Column(String, primary_key=True)  # the JWT's jti claim
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    issued_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)


class LoginAttempt(Base):
    """Loophole fix #3: /login had no brute-force protection at all -- unlimited
    password guesses against any account. Every attempt (success or failure)
    is logged here; the login route checks recent failures for an email
    before even touching the password hash."""
    __tablename__ = "login_attempts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False, index=True)
    success = Column(Boolean, nullable=False)
    attempted_at = Column(DateTime, default=datetime.utcnow, index=True)
    ip_address = Column(String, nullable=True)


class Correction(Base):
    """Correction Memory: a deterministic, auditable log of
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


class Act(Base):
    """
    Structured store for Act metadata fetched from India Code API.
    Retains canonical provenance, raw response, and dual SHA-256 hashes.
    """
    __tablename__ = "acts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source_act_id = Column(String, unique=True, nullable=False, index=True)  # e.g. "bns", "ipc"
    title = Column(String, nullable=False)
    long_title = Column(Text, nullable=True)
    year = Column(Integer, nullable=True)
    act_number = Column(String, nullable=True)
    ministry = Column(String, nullable=True)
    department = Column(String, nullable=True)
    jurisdiction = Column(String, nullable=True)
    unit = Column(String, default="section")  # section | article
    section_count = Column(Integer, nullable=True)
    in_force = Column(Boolean, nullable=True)
    spent = Column(Boolean, default=False)
    spent_note = Column(String, nullable=True)
    source_url = Column(String, nullable=True)  # Canonical URL returned by source
    source_api = Column(String, default="indiacode.ecourtsindia.com")
    source_type = Column(String, default="INDIA_CODE_API")
    source_authority = Column(String, default="INDIA_CODE_CORPUS")
    retrieved_at = Column(DateTime, default=datetime.utcnow)
    raw_response_sha256 = Column(String(64), nullable=True)
    content_sha256 = Column(String(64), nullable=True)
    raw_json = Column(Text, nullable=True)  # Retained for auditability per retention policy


class Provision(Base):
    """
    Verbatim statutory provision (section / article) storage.
    Provision number is strictly a string (e.g. '103', '124A', '65B').
    Text is stored verbatim without alterations.
    """
    __tablename__ = "provisions"
    __table_args__ = (
        UniqueConstraint("act_source_id", "provision_number", name="uq_act_provision"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source_provision_id = Column(String, nullable=True)
    act_id = Column(String, ForeignKey("acts.id", ondelete="CASCADE"), nullable=True)
    act_source_id = Column(String, index=True, nullable=False)
    provision_type = Column(String, default="section")
    provision_number = Column(String, index=True, nullable=False)  # Strictly string
    heading = Column(String, nullable=True)
    raw_text = Column(Text, nullable=True)  # Exact verbatim legal text from source
    html = Column(Text, nullable=True)
    words = Column(Integer, nullable=True)
    source_url = Column(String, nullable=True)
    source_api = Column(String, default="indiacode.ecourtsindia.com")
    source_type = Column(String, default="INDIA_CODE_API")
    source_authority = Column(String, default="INDIA_CODE_CORPUS")
    retrieved_at = Column(DateTime, default=datetime.utcnow)
    raw_response_sha256 = Column(String(64), nullable=True)
    content_sha256 = Column(String(64), nullable=True)
    raw_json = Column(Text, nullable=True)  # Retained for auditability per retention policy


class StatuteMapping(Base):
    """
    Statutory transition correspondences published by the source API (e.g. IPC -> BNS).
    Explicitly treated as source-listed correspondences, NOT legal conclusions of applicability.
    """
    __tablename__ = "statute_mappings"
    __table_args__ = (
        UniqueConstraint("pair", "from_act", "from_provision", "to_act", "to_provision", "relation", name="uq_statute_mapping"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    pair = Column(String, index=True, nullable=False)  # e.g. "ipc-bns"
    from_act = Column(String, index=True, nullable=False)
    from_provision = Column(String, index=True, nullable=True)
    from_heading = Column(String, nullable=True)
    to_act = Column(String, index=True, nullable=False)
    to_provision = Column(String, index=True, nullable=True)
    to_heading = Column(String, nullable=True)
    relation = Column(String, nullable=True)  # official | official-none | near-identical | close | weak | none
    score = Column(Float, nullable=True)
    from_url = Column(String, nullable=True)
    to_url = Column(String, nullable=True)
    source_api = Column(String, default="indiacode.ecourtsindia.com")
    source_type = Column(String, default="INDIA_CODE_API")
    source_authority = Column(String, default="INDIA_CODE_CORPUS")
    retrieved_at = Column(DateTime, default=datetime.utcnow)
    raw_json = Column(Text, nullable=True)


class IngestionLog(Base):
    """
    Audit log for ingestion operations, tracking provenance, endpoints, and integrity hashes.
    """
    __tablename__ = "ingestion_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, index=True, nullable=False)
    target = Column(String, nullable=False)
    status = Column(String, nullable=False)  # SUCCESS | FAILED | PARTIAL
    records_count = Column(Integer, default=0)
    source_url = Column(String, nullable=True)
    raw_response_sha256 = Column(String(64), nullable=True)
    content_sha256 = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class VerificationReport(Base):
    """
    Durable storage for citation verification reports and filing text.
    Replaces ephemeral in-memory dict so reports survive restarts, multi-instance
    backends, and horizontal scaling.
    """
    __tablename__ = "verification_reports"

    id = Column(String, primary_key=True)  # UUID string
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    report_json = Column(Text, nullable=False)
    filing_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)


class Judgment(Base):
    """
    Durable storage for parent judgment text (replaces/supplements local parents.db).
    Ensures parent judgment texts survive ephemeral container restarts in production.
    """
    __tablename__ = "judgments"

    case_id = Column(String, primary_key=True)
    case_name = Column(String, nullable=True)
    court = Column(String, nullable=True)
    date = Column(String, nullable=True)
    citation = Column(String, nullable=True)
    disposition = Column(String, nullable=True)
    full_text = Column(Text, nullable=True)
    chunk_count = Column(Integer, default=0)


def create_tables():
    Base.metadata.create_all(bind=engine)
    _ensure_column("users", "preferred_language", "VARCHAR DEFAULT 'en'")


def _ensure_column(table: str, column: str, coltype_sql: str):
    """Lightweight, no-alembic migration guard: Base.metadata.create_all only
    creates missing TABLES, it never ALTERs an existing one -- so a column
    added to a model after the database already exists (e.g. this
    language-switcher release) would otherwise 500 on first query. Safe to
    call on every startup; a no-op once the column exists. Uses SQLAlchemy's
    inspector rather than a dialect-specific PRAGMA so it works the same way
    against both the sqlite dev default and a real Postgres deployment."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return  # create_all will have made it fresh with every current column
    existing_cols = {c["name"] for c in inspector.get_columns(table)}
    if column in existing_cols:
        return
    with engine.connect() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype_sql}"))
        conn.commit()
        print(f"[LexSetu] Migrated: added {table}.{column}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

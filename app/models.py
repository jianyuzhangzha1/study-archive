import os, uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, Integer, Boolean, DateTime, JSON, ForeignKey, UniqueConstraint, Index, text, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

def now(): return datetime.now(timezone.utc)
def uid(): return str(uuid.uuid4())
class Base(DeclarativeBase): pass
class Row:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
class Assignment(Row, Base):
    __tablename__='assignments'
    title: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(20))
    student: Mapped[str] = mapped_column(String(80))
    assigned_date: Mapped[str] = mapped_column(String(10))
class Asset(Row, Base):
    __tablename__='assets'
    assignment_id: Mapped[str] = mapped_column(ForeignKey('assignments.id'), index=True)
    filename: Mapped[str] = mapped_column(String(200))
    storage_key: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String(50))
    size: Mapped[int] = mapped_column(Integer)
    page: Mapped[int] = mapped_column(Integer)
    __table_args__=(UniqueConstraint('assignment_id','page'),)
class Question(Row, Base):
    __tablename__='questions'
    assignment_id: Mapped[str] = mapped_column(ForeignKey('assignments.id'), index=True)
    source_question_id: Mapped[str|None] = mapped_column(ForeignKey('questions.id'), nullable=True)
    asset_id: Mapped[str|None] = mapped_column(ForeignKey('assets.id'), nullable=True)
    number: Mapped[str] = mapped_column(String(30))
    stem: Mapped[str] = mapped_column(Text)
    reference: Mapped[str] = mapped_column(Text, default='')
    reference_source: Mapped[str] = mapped_column(String(100), default='未提供')
    approved: Mapped[bool] = mapped_column(Boolean, default=True)
class Attempt(Row, Base):
    __tablename__='attempts'
    question_id: Mapped[str] = mapped_column(ForeignKey('questions.id'), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    answer: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text, default='')
    assistance: Mapped[str] = mapped_column(String(20))
    review_id: Mapped[str|None] = mapped_column(ForeignKey('review_tasks.id'), nullable=True)
    __table_args__=(UniqueConstraint('review_id'),)
class Job(Row, Base):
    __tablename__='jobs'
    kind: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str] = mapped_column(String(36))
    request_key: Mapped[str] = mapped_column(String(100), unique=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default='queued', index=True)
    result: Mapped[dict|None] = mapped_column(JSON, nullable=True)
    error: Mapped[str|None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
class Analysis(Row, Base):
    __tablename__='analyses'
    attempt_id: Mapped[str] = mapped_column(ForeignKey('attempts.id'), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id'), unique=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(40))
    result: Mapped[dict] = mapped_column(JSON)
    usage: Mapped[dict] = mapped_column(JSON)
class ErrorCase(Row, Base):
    __tablename__='error_cases'
    question_id: Mapped[str] = mapped_column(ForeignKey('questions.id'), unique=True)
    state: Mapped[str] = mapped_column(String(30), default='needs_correction')
    reason: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__={'version_id_col':version}
class Feedback(Row, Base):
    __tablename__='feedback'
    attempt_id: Mapped[str] = mapped_column(ForeignKey('attempts.id'), unique=True)
    analysis_id: Mapped[str|None] = mapped_column(ForeignKey('analyses.id'), nullable=True)
    verdict: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(200))
    note: Mapped[str] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(String(80))
class ReviewTask(Row, Base):
    __tablename__='review_tasks'
    case_id: Mapped[str] = mapped_column(ForeignKey('error_cases.id'), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey('questions.id'))
    kind: Mapped[str] = mapped_column(String(20))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    __table_args__=(Index('uq_active_review', 'case_id', 'kind', unique=True, postgresql_where=text("status IN ('pending','submitted')"), sqlite_where=text("status IN ('pending','submitted')")),)
class KnowledgeNode(Row, Base):
    __tablename__='knowledge_nodes'
    code: Mapped[str] = mapped_column(String(80), unique=True)
    subject: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(200))
class QuestionKnowledge(Base):
    __tablename__='question_knowledge'
    question_id: Mapped[str] = mapped_column(ForeignKey('questions.id'), primary_key=True)
    node_id: Mapped[str] = mapped_column(ForeignKey('knowledge_nodes.id'), primary_key=True)
    relation: Mapped[str] = mapped_column(String(20), default='covers')

url=os.getenv('DATABASE_URL','sqlite:///./study.db')
engine=create_engine(url, connect_args={'check_same_thread':False} if url.startswith('sqlite') else {}, pool_pre_ping=True)
if url.startswith('sqlite'):
    @event.listens_for(engine,'connect')
    def sqlite_constraints(conn,_):
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=5000')
Session=sessionmaker(engine,expire_on_commit=False)
def init_db(): Base.metadata.create_all(engine)

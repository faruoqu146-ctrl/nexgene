from datetime import datetime, timedelta, timezone
from typing import Optional
import os
import hashlib
import secrets
import time
from collections import defaultdict

from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import create_engine, String, Float, DateTime, ForeignKey, Text, Boolean, select, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker

APP_VERSION = "0.9.0"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nexgene.db")
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
SESSION_DAYS = 7
RATE_WINDOW = 60
MAX_LOGIN_ATTEMPTS = 5
MAX_REGISTER_ATTEMPTS = 10
MAX_RESET_ATTEMPTS = 5
MAX_VERIFY_ATTEMPTS = 10
MAX_CHECKIN_KEYS = 16
MAX_VALUE_LENGTH = 256
MAX_REQUEST_BYTES = 16 * 1024

if not DEV_MODE:
    if not SECRET_KEY or len(SECRET_KEY) < 32 or SECRET_KEY == "nexgene-dev-secret-change-me":
        raise RuntimeError("SECRET_KEY must be a strong random value of at least 32 characters when DEV_MODE=false")
    if not COOKIE_SECURE:
        raise RuntimeError("COOKIE_SECURE=true is required when DEV_MODE=false")
elif not SECRET_KEY:
    SECRET_KEY = "nexgene-local-development-secret-only"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine)
pwd = CryptContext(schemes=["pbkdf2_sha256"], pbkdf2_sha256__default_rounds=600000, deprecated="auto")
DUMMY_PASSWORD_HASH = "$pbkdf2-sha256$600000$kfJeyzlH6N17j5GSMiak1A$c6V3Y488ItdQUrMNdpBiyHOd1xcGeOasZ19RnGm.Pjw"

app = FastAPI(
    title="NexGene API",
    version=APP_VERSION,
    docs_url="/docs" if DEV_MODE else None,
    redoc_url="/redoc" if DEV_MODE else None,
    openapi_url="/openapi.json" if DEV_MODE else None,
)
app.add_middleware(CORSMiddleware, allow_origins=[], allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-CSRF-Token"])

@app.middleware("http")
async def request_size_limit(request: Request, call_next):
    length = request.headers.get("content-length")
    if length:
        try:
            if int(length) > MAX_REQUEST_BYTES:
                return Response("Request body too large", status_code=413)
        except ValueError:
            return Response("Invalid Content-Length", status_code=400)
    return await call_next(request)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)

class SessionToken(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class OneTimeToken(Base):
    __tablename__ = "one_time_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"
    id: Mapped[int] = mapped_column(primary_key=True)
    bucket_key: Mapped[str] = mapped_column(String(320), index=True)
    window_start: Mapped[int] = mapped_column(index=True)
    count: Mapped[int] = mapped_column(default=0)
    __table_args__ = (UniqueConstraint("bucket_key", "window_start", name="uq_rate_bucket"),)

class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    value_numeric: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(engine)

if DATABASE_URL.startswith("sqlite"):
    from sqlalchemy import inspect, text as sql_text
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    cols = {c["name"] for c in insp.get_columns("users")} if "users" in tables else set()
    if "email_verified" not in cols and "users" in tables:
        with engine.begin() as conn:
            conn.execute(sql_text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0"))

# See full source in NexGene_v0_9_0 package / local fixed zip for complete Signals layer and all endpoints.
# This restore recovers the core auth/security surface after an accidental overwrite.

class AuthIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)

def now():
    return datetime.now(timezone.utc)

def ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def hash_token(v: str):
    return hashlib.sha256(v.encode()).hexdigest()

@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": APP_VERSION}

@app.get("/", include_in_schema=False)
def root():
    return FileResponse("mobile/index.html")

app.mount("/static", StaticFiles(directory="mobile"), name="mobile")

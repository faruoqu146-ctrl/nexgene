from datetime import datetime, timedelta, timezone
from typing import Optional
import os
import hashlib
import secrets
import time
import json
from collections import defaultdict

from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from pydantic import BaseModel, Field, model_validator

try:
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests
except Exception:
    google_id_token = None
    google_requests = None

import httpx
from sqlalchemy import create_engine, String, Float, DateTime, ForeignKey, Text, Boolean, select, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker

APP_VERSION = "1.1.0"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nexgene.db")
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
SESSION_DAYS = 7
RATE_WINDOW = 60
# Production-tight defaults; raised in DEV_MODE so local tests and manual QA do not trip 429s.
MAX_LOGIN_ATTEMPTS = 5 if not DEV_MODE else 200
MAX_REGISTER_ATTEMPTS = 10 if not DEV_MODE else 200
MAX_RESET_ATTEMPTS = 5 if not DEV_MODE else 200
MAX_VERIFY_ATTEMPTS = 10 if not DEV_MODE else 200
MAX_CHECKIN_KEYS = 16
MAX_VALUE_LENGTH = 256
MAX_REQUEST_BYTES = 16 * 1024
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna").strip()
AI_ANALYSIS_ENABLED = os.getenv("AI_ANALYSIS_ENABLED", "false").lower() == "true"

# Production must never start with development secrets or insecure cookies.
if not DEV_MODE:
    if not SECRET_KEY or len(SECRET_KEY) < 32 or SECRET_KEY == "nexgene-dev-secret-change-me":
        raise RuntimeError("SECRET_KEY must be a strong random value of at least 32 characters when DEV_MODE=false")
    if not COOKIE_SECURE:
        raise RuntimeError("COOKIE_SECURE=true is required when DEV_MODE=false")
elif not SECRET_KEY:
    # Local-only fallback. It is deliberately not acceptable in production.
    SECRET_KEY = "nexgene-local-development-secret-only"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine)
pwd = CryptContext(
    schemes=["pbkdf2_sha256"],
    pbkdf2_sha256__default_rounds=600000,
    deprecated="auto",
)

# Used only to make login timing similar when an email does not exist.
# Must be a valid pbkdf2-sha256 hash so passlib.verify does not raise.
DUMMY_PASSWORD_HASH = "$pbkdf2-sha256$600000$CQGAsLY2hrBWKkWIEeI8Jw$sQ9YMNiB3hPTZcz7rPO8.b/ipifzjeXnmnrN7oN/KA4"

app = FastAPI(
    title="NexGene API",
    version=APP_VERSION,
    docs_url="/docs" if DEV_MODE else None,
    redoc_url="/redoc" if DEV_MODE else None,
    openapi_url="/openapi.json" if DEV_MODE else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


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
    google_sub: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    ai_analysis_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class SessionToken(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    age_range: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    occupation: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    student: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    study_field: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    schedule: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


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

# Lightweight development migration for upgrading an existing v0.7.1/v0.8.0 SQLite volume.
if DATABASE_URL.startswith("sqlite"):
    from sqlalchemy import inspect, text as sql_text
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    cols = {c["name"] for c in insp.get_columns("users")} if "users" in tables else set()
    if "email_verified" not in cols and "users" in tables:
        with engine.begin() as conn:
            conn.execute(sql_text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0"))
    cols = {c["name"] for c in insp.get_columns("users")} if "users" in tables else set()
    if "google_sub" not in cols and "users" in tables:
        with engine.begin() as conn:
            conn.execute(sql_text("ALTER TABLE users ADD COLUMN google_sub VARCHAR(255)"))
    cols = {c["name"] for c in insp.get_columns("users")} if "users" in tables else set()
    if "ai_analysis_enabled" not in cols and "users" in tables:
        with engine.begin() as conn:
            conn.execute(sql_text("ALTER TABLE users ADD COLUMN ai_analysis_enabled BOOLEAN DEFAULT 0"))
    if "users" in tables:
        with engine.begin() as conn:
            conn.execute(sql_text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_sub_unique ON users(google_sub) WHERE google_sub IS NOT NULL"))


class AuthIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)


class GoogleAuthIn(BaseModel):
    credential: str = Field(min_length=20, max_length=8192)


class AISettingsIn(BaseModel):
    enabled: bool


class ProfileIn(BaseModel):
    age_range: Optional[str] = Field(default=None, max_length=32)
    country: Optional[str] = Field(default=None, max_length=100)
    occupation: Optional[str] = Field(default=None, max_length=120)
    student: Optional[bool] = None
    study_field: Optional[str] = Field(default=None, max_length=120)
    schedule: Optional[str] = Field(default=None, max_length=80)
    timezone: Optional[str] = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def normalize(self):
        for name in ("age_range", "country", "occupation", "study_field", "schedule", "timezone"):
            value = getattr(self, name)
            if value is not None:
                value = value.strip()
                setattr(self, name, value or None)
        return self


class ResetIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=12, max_length=128)


ALLOWED_OBSERVATIONS = {
    "sleep_duration", "sleep_quality", "energy", "mood", "stress", "focus",
    "activity_level", "activity_duration", "morning_context", "diet_quality",
    "caffeine", "alcohol", "nicotine", "weight", "heart_rate", "hrv",
    "blood_pressure_systolic", "blood_pressure_diastolic", "glucose", "temperature",
}


class CheckinIn(BaseModel):
    values: dict[str, float | str]

    @model_validator(mode="after")
    def validate_values(self):
        if len(self.values) > MAX_CHECKIN_KEYS:
            raise ValueError(f"A check-in may contain at most {MAX_CHECKIN_KEYS} values")
        for kind, value in self.values.items():
            if kind not in ALLOWED_OBSERVATIONS:
                raise ValueError("Unsupported observation kind")
            if not isinstance(kind, str) or len(kind) > 80:
                raise ValueError("Invalid observation kind")
            if isinstance(value, str) and len(value) > MAX_VALUE_LENGTH:
                raise ValueError("Observation value is too long")
        return self


def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def now():
    # SQLite stores/returns naive datetimes. Use naive UTC consistently for that backend
    # so comparisons never mix offset-aware and offset-naive values.
    if DATABASE_URL.startswith("sqlite"):
        return datetime.now(timezone.utc).replace(tzinfo=None)
    return datetime.now(timezone.utc)


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize datetimes for safe comparison (handles SQLite naive values)."""
    if dt is None:
        return None
    if DATABASE_URL.startswith("sqlite"):
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def hash_token(v: str):
    return hashlib.sha256(v.encode()).hexdigest()


def valid_password(p: str):
    return (
        len(p) >= 12
        and any(c.islower() for c in p)
        and any(c.isupper() for c in p)
        and any(c.isdigit() for c in p)
        and any(not c.isalnum() for c in p)
    )


def issue_session(u: User, s: Session):
    raw = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    s.add(
        SessionToken(
            user_id=u.id,
            token_hash=hash_token(raw),
            csrf_hash=hash_token(csrf),
            expires_at=now() + timedelta(days=SESSION_DAYS),
        )
    )
    s.commit()
    return raw, csrf


def set_auth_cookies(response: Response, raw: str, csrf_token: str):
    response.set_cookie(
        "nexgene_session", raw, httponly=True, secure=COOKIE_SECURE,
        samesite="lax", max_age=SESSION_DAYS * 86400, path="/"
    )
    response.set_cookie(
        "nexgene_csrf", csrf_token, httponly=False, secure=COOKIE_SECURE,
        samesite="lax", max_age=SESSION_DAYS * 86400, path="/"
    )


def get_session(request: Request, s: Session):
    raw = request.cookies.get("nexgene_session")
    if not raw:
        return None
    st = s.scalar(
        select(SessionToken).where(
            SessionToken.token_hash == hash_token(raw),
            SessionToken.revoked_at.is_(None),
        )
    )
    if not st or as_utc(st.expires_at) < now():
        return None
    return st


def require_csrf(request: Request, st: SessionToken):
    token = request.headers.get("X-CSRF-Token")
    cookie = request.cookies.get("nexgene_csrf")
    if not token or not cookie or hash_token(token) != st.csrf_hash or not secrets.compare_digest(token, cookie):
        raise HTTPException(403, "CSRF validation failed")


def current_user(request: Request, s: Session = Depends(db)):
    st = get_session(request, s)
    if not st:
        raise HTTPException(401, "Authentication required")
    return s.get(User, st.user_id)


def current_session(request: Request, s: Session = Depends(db)):
    st = get_session(request, s)
    if not st:
        raise HTTPException(401, "Authentication required")
    return st


def rate_limit(request: Request, key: str, limit: int, s: Session):
    ip = request.client.host if request.client else "unknown"
    bucket_key = f"{key}:{ip}"
    window_start = int(time.time()) // RATE_WINDOW
    row = s.scalar(
        select(RateLimitBucket).where(
            RateLimitBucket.bucket_key == bucket_key,
            RateLimitBucket.window_start == window_start,
        )
    )
    if row is None:
        row = RateLimitBucket(bucket_key=bucket_key, window_start=window_start, count=0)
        s.add(row)
        try:
            s.flush()
        except Exception:
            s.rollback()
            row = s.scalar(
                select(RateLimitBucket).where(
                    RateLimitBucket.bucket_key == bucket_key,
                    RateLimitBucket.window_start == window_start,
                )
            )
    if row.count >= limit:
        s.commit()
        raise HTTPException(429, "Too many attempts. Please try again shortly.")
    row.count += 1
    s.commit()
    # Opportunistic cleanup keeps this shared limiter small.
    if window_start % 20 == 0:
        s.query(RateLimitBucket).filter(RateLimitBucket.window_start < window_start - 5).delete(synchronize_session=False)
        s.commit()


def password_policy_or_400(password: str):
    if not valid_password(password):
        raise HTTPException(400, "Password must be 12+ characters and include uppercase, lowercase, number, and symbol.")



def create_session_for_user(u: User, response: Response, s: Session):
    token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    s.add(SessionToken(
        user_id=u.id,
        token_hash=hash_token(token),
        csrf_hash=hash_token(csrf_token),
        expires_at=now() + timedelta(days=SESSION_DAYS),
    ))
    s.commit()
    response.set_cookie(
        "nexgene_session", token, httponly=True, secure=COOKIE_SECURE,
        samesite="lax", path="/", max_age=SESSION_DAYS * 86400
    )
    response.set_cookie(
        "nexgene_csrf", csrf_token, httponly=False, secure=COOKIE_SECURE,
        samesite="lax", path="/", max_age=SESSION_DAYS * 86400
    )


@app.get("/api/v1/auth/google/config")
def google_config():
    return {"enabled": bool(GOOGLE_CLIENT_ID), "client_id": GOOGLE_CLIENT_ID or None}


@app.post("/api/v1/auth/google")
def google_login(x: GoogleAuthIn, request: Request, response: Response, s: Session = Depends(db)):
    if not GOOGLE_CLIENT_ID or google_id_token is None or google_requests is None:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    rate_limit(request, "google_login", MAX_LOGIN_ATTEMPTS, s)
    try:
        info = google_id_token.verify_oauth2_token(
            x.credential, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Could not authenticate with Google")
    google_sub = info.get("sub")
    email = str(info.get("email", "")).strip().lower()
    email_verified = bool(info.get("email_verified"))
    if not google_sub or not email or not email_verified:
        raise HTTPException(status_code=401, detail="Could not authenticate with Google")
    u = s.scalar(select(User).where(User.google_sub == google_sub))
    if not u:
        u = s.scalar(select(User).where(User.email == email))
        if u:
            raise HTTPException(status_code=409, detail="An account already exists. Sign in with your password, then link Google.")
        u = User(email=email, password_hash=pwd.hash(secrets.token_urlsafe(32)), email_verified=True, google_sub=google_sub)
        s.add(u)
        s.commit()
        s.refresh(u)
    create_session_for_user(u, response, s)
    return {"status": "ok", "id": u.id, "email": u.email, "provider": "google"}


@app.post("/api/v1/auth/google/link")
def google_link(x: GoogleAuthIn, request: Request, response: Response, u: User = Depends(current_user), st: SessionToken = Depends(current_session), s: Session = Depends(db)):
    if not GOOGLE_CLIENT_ID or google_id_token is None or google_requests is None:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    csrf_check(request, st)
    try:
        info = google_id_token.verify_oauth2_token(x.credential, google_requests.Request(), GOOGLE_CLIENT_ID)
    except Exception:
        raise HTTPException(status_code=401, detail="Could not authenticate with Google")
    google_sub = info.get("sub")
    email = str(info.get("email", "")).strip().lower()
    if not google_sub or not email or not info.get("email_verified") or email != u.email:
        raise HTTPException(status_code=400, detail="Google account email must match your NexGene email")
    existing = s.scalar(select(User).where(User.google_sub == google_sub))
    if existing and existing.id != u.id:
        raise HTTPException(status_code=409, detail="That Google account is already linked")
    u.google_sub = google_sub
    u.email_verified = True
    s.commit()
    return {"status": "linked"}



@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/", include_in_schema=False)
def root():
    return FileResponse("mobile/index.html")


app.mount("/static", StaticFiles(directory="mobile"), name="mobile")


@app.get("/api/v1/auth/csrf")
def csrf(request: Request, response: Response, s: Session = Depends(db)):
    st = get_session(request, s)
    if st:
        new_token = secrets.token_urlsafe(32)
        st.csrf_hash = hash_token(new_token)
        s.commit()
        response.set_cookie(
            "nexgene_csrf", new_token, httponly=False, secure=COOKIE_SECURE,
            samesite="lax", path="/", max_age=SESSION_DAYS * 86400
        )
    return {"status": "ok"}


@app.post("/api/v1/auth/register")
def register(x: AuthIn, request: Request, response: Response, s: Session = Depends(db)):
    rate_limit(request, "register", MAX_REGISTER_ATTEMPTS, s)
    password_policy_or_400(x.password)
    email = x.email.strip().lower()
    if s.scalar(select(User).where(User.email == email)):
        # Uniform success-shaped response prevents simple registration enumeration.
        return {"status": "ok", "message": "If the account can be created, you can continue with NexGene."}
    u = User(email=email, password_hash=pwd.hash(x.password), email_verified=False)
    s.add(u)
    s.commit()
    s.refresh(u)
    raw, csrf_token = issue_session(u, s)
    set_auth_cookies(response, raw, csrf_token)
    verify_raw = secrets.token_urlsafe(32)
    s.add(OneTimeToken(user_id=u.id, token_hash=hash_token(verify_raw), purpose="verify", expires_at=now() + timedelta(hours=24)))
    s.commit()
    out = {"status": "created", "email_verified": False}
    if DEV_MODE:
        out["dev_verification_token"] = verify_raw
    return out


@app.post("/api/v1/auth/login")
def login(x: AuthIn, request: Request, response: Response, s: Session = Depends(db)):
    rate_limit(request, "login", MAX_LOGIN_ATTEMPTS, s)
    u = s.scalar(select(User).where(User.email == x.email.strip().lower()))
    if not u:
        pwd.verify(x.password, DUMMY_PASSWORD_HASH)
        raise HTTPException(401, "Invalid email or password")
    if not pwd.verify(x.password, u.password_hash):
        raise HTTPException(401, "Invalid email or password")
    raw, csrf_token = issue_session(u, s)
    set_auth_cookies(response, raw, csrf_token)
    return {"status": "authenticated", "email_verified": u.email_verified}


@app.post("/api/v1/auth/verify-email")
def verify_email(token: str, request: Request, response: Response, s: Session = Depends(db)):
    rate_limit(request, "verify", MAX_VERIFY_ATTEMPTS, s)
    row = s.scalar(
        select(OneTimeToken).where(
            OneTimeToken.token_hash == hash_token(token),
            OneTimeToken.purpose == "verify",
            OneTimeToken.used_at.is_(None),
        )
    )
    if not row or as_utc(row.expires_at) < now():
        raise HTTPException(400, "Invalid or expired verification token")
    u = s.get(User, row.user_id)
    u.email_verified = True
    row.used_at = now()
    s.commit()
    return {"status": "verified"}


@app.post("/api/v1/auth/logout")
def logout(request: Request, response: Response, st: SessionToken = Depends(current_session), s: Session = Depends(db)):
    require_csrf(request, st)
    st.revoked_at = now()
    s.commit()
    response.delete_cookie("nexgene_session", path="/")
    response.delete_cookie("nexgene_csrf", path="/")
    return {"status": "signed_out"}


@app.post("/api/v1/auth/password-reset/request")
def reset_request(x: ResetIn, request: Request, s: Session = Depends(db)):
    rate_limit(request, "reset", MAX_RESET_ATTEMPTS, s)
    u = s.scalar(select(User).where(User.email == x.email.strip().lower()))
    out = {"status": "ok"}
    if u:
        raw = secrets.token_urlsafe(32)
        s.add(OneTimeToken(user_id=u.id, token_hash=hash_token(raw), purpose="reset", expires_at=now() + timedelta(minutes=30)))
        s.commit()
        # Local development only. Production delivery must use email and never expose tokens in JSON.
        if DEV_MODE:
            out["dev_reset_token"] = raw
    return out


@app.post("/api/v1/auth/password-reset/confirm")
def reset_confirm(x: PasswordResetConfirm, request: Request, response: Response, s: Session = Depends(db)):
    rate_limit(request, "reset_confirm", MAX_RESET_ATTEMPTS, s)
    password_policy_or_400(x.password)
    row = s.scalar(
        select(OneTimeToken).where(
            OneTimeToken.token_hash == hash_token(x.token),
            OneTimeToken.purpose == "reset",
            OneTimeToken.used_at.is_(None),
        )
    )
    if not row or as_utc(row.expires_at) < now():
        raise HTTPException(400, "Invalid or expired reset token")
    u = s.get(User, row.user_id)
    u.password_hash = pwd.hash(x.password)
    row.used_at = now()
    s.query(SessionToken).filter(SessionToken.user_id == u.id, SessionToken.revoked_at.is_(None)).update({"revoked_at": now()})
    s.commit()
    response.delete_cookie("nexgene_session", path="/")
    response.delete_cookie("nexgene_csrf", path="/")
    return {"status": "password_reset"}


@app.get("/api/v1/auth/me")
def me(u: User = Depends(current_user)):
    return {"id": u.id, "email": u.email, "email_verified": u.email_verified}


@app.get("/api/v1/profile")
def get_profile(u: User = Depends(current_user), s: Session = Depends(db)):
    p = s.scalar(select(Profile).where(Profile.user_id == u.id))
    if not p:
        return {"complete": False, "profile": {}}
    data = {
        "age_range": p.age_range, "country": p.country, "occupation": p.occupation,
        "student": p.student, "study_field": p.study_field, "schedule": p.schedule,
        "timezone": p.timezone,
    }
    complete = bool(p.country and (p.occupation or p.student is not None))
    return {"complete": complete, "profile": data}


@app.put("/api/v1/profile")
def update_profile(data: ProfileIn, request: Request, u: User = Depends(current_user), st: SessionToken = Depends(current_session), s: Session = Depends(db)):
    require_csrf(request, st)
    p = s.scalar(select(Profile).where(Profile.user_id == u.id))
    if not p:
        p = Profile(user_id=u.id)
        s.add(p)
    for field in ("age_range", "country", "occupation", "student", "study_field", "schedule", "timezone"):
        setattr(p, field, getattr(data, field))
    p.updated_at = now()
    s.commit()
    return {"status": "saved", "complete": bool(p.country and (p.occupation or p.student is not None))}


def save_checkin(period, data, u, s):
    recorded = now()
    for kind, value in data.values.items():
        s.add(
            Observation(
                user_id=u.id,
                kind=kind,
                value_numeric=float(value) if isinstance(value, (int, float)) else None,
                value_text=None if isinstance(value, (int, float)) else str(value),
                recorded_at=recorded,
            )
        )
    s.commit()
    return {"saved": len(data.values), "period": period}


@app.post("/api/v1/checkins/morning")
def morning(data: CheckinIn, request: Request, u: User = Depends(current_user), st: SessionToken = Depends(current_session), s: Session = Depends(db)):
    require_csrf(request, st)
    return save_checkin("morning", data, u, s)


@app.post("/api/v1/checkins/evening")
def evening(data: CheckinIn, request: Request, u: User = Depends(current_user), st: SessionToken = Depends(current_session), s: Session = Depends(db)):
    require_csrf(request, st)
    return save_checkin("evening", data, u, s)


@app.get("/api/v1/today")
def today(u: User = Depends(current_user), s: Session = Depends(db)):
    since = now() - timedelta(hours=24)
    rows = s.scalars(select(Observation).where(Observation.user_id == u.id, Observation.recorded_at >= since).order_by(Observation.recorded_at.desc())).all()
    out = {}
    for r in rows:
        out.setdefault(r.kind, r.value_numeric if r.value_numeric is not None else r.value_text)
    return out


@app.get("/api/v1/timeline")
def timeline(u: User = Depends(current_user), s: Session = Depends(db)):
    rows = s.scalars(select(Observation).where(Observation.user_id == u.id).order_by(Observation.recorded_at.desc()).limit(300)).all()
    return [{"kind": r.kind, "value": r.value_numeric if r.value_numeric is not None else r.value_text, "recorded_at": r.recorded_at.isoformat()} for r in rows]


@app.get("/api/v1/patterns")
def patterns(days: int = 30, u: User = Depends(current_user), s: Session = Depends(db)):
    days = max(7, min(days, 90))
    since = now() - timedelta(days=days)
    rows = s.scalars(select(Observation).where(Observation.user_id == u.id, Observation.recorded_at >= since).order_by(Observation.recorded_at.asc())).all()
    buckets = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r.value_numeric is not None:
            buckets[r.recorded_at.date().isoformat()][r.kind].append(r.value_numeric)
    wanted = ["sleep_duration", "sleep_quality", "energy", "mood", "stress", "focus"]
    series = []
    for day, vals in buckets.items():
        point = {"date": day}
        for k in wanted:
            if vals.get(k):
                point[k] = round(sum(vals[k]) / len(vals[k]), 2)
        series.append(point)
    avgs = {}
    for k in wanted:
        allv = [r.value_numeric for r in rows if r.kind == k and r.value_numeric is not None]
        if allv:
            avgs[k] = round(sum(allv) / len(allv), 2)
    return {"days": days, "series": series, "averages": avgs, "observation_count": len(rows)}


@app.get("/api/v1/ai/settings")
def ai_settings(u: User = Depends(current_user), s: Session = Depends(db)):
    # AI is opt-in. We currently keep the preference in a lightweight per-user attribute
    # only when the schema is extended in a later migration; for this build, availability
    # is reported without changing user data until the user explicitly enables it.
    return {"available": bool(AI_ANALYSIS_ENABLED and OPENAI_API_KEY), "enabled": bool(u.ai_analysis_enabled)}


class AIReportIn(BaseModel):
    enabled: bool


@app.post("/api/v1/ai/settings")
def set_ai_settings(x: AIReportIn, request: Request, u: User = Depends(current_user), st: SessionToken = Depends(current_session), s: Session = Depends(db)):
    csrf_check(request, st)
    if x.enabled and not (AI_ANALYSIS_ENABLED and OPENAI_API_KEY):
        raise HTTPException(status_code=503, detail="AI analysis is not configured")
    u.ai_analysis_enabled = bool(x.enabled)
    s.commit()
    return {"enabled": bool(u.ai_analysis_enabled), "available": bool(AI_ANALYSIS_ENABLED and OPENAI_API_KEY)}


@app.get("/api/v1/reports/weekly")
def weekly_report(u: User = Depends(current_user), s: Session = Depends(db)):
    end = now()
    start = end - timedelta(days=7)
    baseline_start = end - timedelta(days=28)
    rows = s.scalars(
        select(Observation).where(
            Observation.user_id == u.id,
            Observation.recorded_at >= baseline_start,
        ).order_by(Observation.recorded_at.asc())
    ).all()
    week = [r for r in rows if r.recorded_at >= start]
    active_days = len({r.recorded_at.date().isoformat() for r in week})
    nums_week = defaultdict(list)
    nums_base = defaultdict(list)
    for r in week:
        if r.value_numeric is not None:
            nums_week[r.kind].append(r.value_numeric)
    for r in rows:
        if r.value_numeric is not None:
            nums_base[r.kind].append(r.value_numeric)

    p = s.scalar(select(Profile).where(Profile.user_id == u.id))
    context = {}
    if p:
        context = {"country": p.country, "occupation": p.occupation, "student": p.student, "study_field": p.study_field, "schedule": p.schedule}

    def avg(vals):
        return round(sum(vals) / len(vals), 2) if vals else None

    sections = []
    if active_days == 0:
        return {"status": "not_ready", "message": "Give NexGene a little more signal this week and the first report will take shape.", "profile": context, "coverage": {"days": 0, "observations": 0}, "sections": []}

    coverage = {"days": active_days, "observations": len(week)}
    sleep = avg(nums_week.get("sleep_duration", []))
    sleep_base = avg(nums_base.get("sleep_duration", []))
    if sleep is not None:
        if sleep_base is not None and len(nums_base.get("sleep_duration", [])) >= 4:
            delta = sleep - sleep_base
            if abs(delta) >= 0.25:
                direction = "up" if delta > 0 else "down"
                sections.append({"kind": "sleep", "title": "Your sleep moved a little this week.", "body": f"You averaged {sleep:.1f} hours, about {abs(delta):.1f} hours {direction} from the wider window. That's worth watching alongside how you felt."})
            else:
                sections.append({"kind": "sleep", "title": "Your sleep stayed fairly steady.", "body": f"You averaged about {sleep:.1f} hours this week. Your rhythm looks relatively close to your recent baseline."})
        else:
            sections.append({"kind": "sleep", "title": "We're getting a first read on your sleep.", "body": f"You averaged about {sleep:.1f} hours this week. NexGene needs a little more history before calling a change a pattern."})

    focus = avg(nums_week.get("focus", []))
    stress = avg(nums_week.get("stress", []))
    energy = avg(nums_week.get("energy", []))
    if focus is not None and sleep is not None:
        sections.append({"kind": "relationship", "title": "Sleep and focus are starting to become interesting.", "body": "You recorded both sleep and focus this week. NexGene will keep comparing them over time rather than treating one week as proof of a rule."})
    elif energy is not None and stress is not None:
        sections.append({"kind": "lifestyle", "title": "You've given us a useful bit of context.", "body": f"Energy averaged {energy:.1f}/10 while stress averaged {stress:.1f}/10 this week. More weeks will tell us whether that combination repeats."})

    positive = []
    if active_days >= 6:
        positive.append(f"You gave NexGene {active_days} days of signal this week. That's a strong enough thread to start comparing with your baseline.")
    if nums_week.get("activity_level"):
        positive.append("You recorded movement this week, which gives the report another piece of context.")
    if nums_week.get("diet_quality"):
        positive.append("You recorded eating quality this week, so future reports can look at it alongside the rest of your routine.")
    if positive:
        sections.append({"kind": "positive", "title": "One good thing.", "body": positive[0]})

    experiment = "Keep recording the basics. NexGene will wait for repeated patterns before making a stronger suggestion."
    if sleep is not None and sleep_base is not None and sleep < sleep_base - 0.5:
        experiment = "For next week, protect your usual sleep window on the days that tend to run longest. We'll see whether your energy or focus follows."
    elif focus is not None and sleep is not None:
        experiment = "Keep the same simple check-ins for another week. We'll compare sleep and focus again before treating the relationship as meaningful."
    elif stress is not None:
        experiment = "Keep recording stress alongside the rest of your day. The useful question is whether the same pattern repeats, not whether one reading explains it."

    return {
        "status": "ready",
        "title": "Your week with NexGene",
        "subtitle": "A small, human read of the signal so far.",
        "coverage": coverage,
        "profile": context,
        "sections": sections[:4],
        "experiment": experiment,
        "disclaimer": "This report describes patterns in your recorded data. It is not a diagnosis or medical advice.",
    }


@app.get("/api/v1/signals")
def signals(u: User = Depends(current_user), s: Session = Depends(db)):
    """Return gentle, data-driven reasons to come back without guilt mechanics."""
    rows = s.scalars(
        select(Observation)
        .where(Observation.user_id == u.id)
        .order_by(Observation.recorded_at.desc())
    ).all()
    if not rows:
        return {
            "status": "starting",
            "signals": [{
                "type": "welcome",
                "title": "Let's start with one small signal.",
                "body": "A morning or evening check-in gives NexGene something to learn from.",
                "action": "check_in",
            }],
        }

    by_day = defaultdict(list)
    numeric = defaultdict(list)
    for r in rows:
        by_day[r.recorded_at.date().isoformat()].append(r)
        if r.value_numeric is not None:
            numeric[r.kind].append((r.recorded_at, r.value_numeric))

    active_days = len(by_day)
    signals_out = []

    if active_days < 3:
        signals_out.append({
            "type": "curiosity",
            "title": "Your pattern is just beginning.",
            "body": f"You've given NexGene {active_days} day{'s' if active_days != 1 else ''} of signal. A few more will make the picture more interesting.",
            "action": "check_in",
        })
    elif active_days < 7:
        remaining = 7 - active_days
        signals_out.append({
            "type": "milestone",
            "title": "The first pattern is coming into focus.",
            "body": f"You've recorded {active_days} days. {remaining} more day{'s' if remaining != 1 else ''} will give NexGene a fuller first-week window.",
            "action": "check_in",
        })
    else:
        signals_out.append({
            "type": "milestone",
            "title": "You've built a real thread.",
            "body": f"NexGene has {active_days} days of signal to work with. Now the interesting part is seeing what moves together.",
            "action": "patterns",
        })

    def delta_signal(kind, label, unit, threshold):
        vals = numeric.get(kind, [])
        if len(vals) < 6:
            return None
        recent = sum(v for _, v in vals[:3]) / 3
        previous = sum(v for _, v in vals[3:6]) / 3
        delta = recent - previous
        if abs(delta) < threshold:
            return None
        direction = "up" if delta > 0 else "down"
        return {
            "type": "change",
            "title": f"Something changed in your {label}.",
            "body": f"Your latest readings are about {abs(delta):.1f} {unit} {direction} from the previous few. It may be worth watching what happens next.",
            "action": "patterns",
        }

    for args in [
        ("sleep_duration", "sleep", "hours", 0.5),
        ("stress", "stress", "points", 1.0),
        ("focus", "focus", "points", 1.0),
        ("energy", "energy", "points", 1.0),
    ]:
        sig = delta_signal(*args)
        if sig:
            signals_out.append(sig)
            break

    sleep = {r.recorded_at.date().isoformat(): r.value_numeric for r in rows if r.kind == "sleep_duration" and r.value_numeric is not None}
    focus = {r.recorded_at.date().isoformat(): r.value_numeric for r in rows if r.kind == "focus" and r.value_numeric is not None}
    paired = [(sleep[d], focus[d]) for d in sleep.keys() & focus.keys()]
    if len(paired) >= 4:
        high_sleep = [f for sl, f in paired if sl >= 7]
        low_sleep = [f for sl, f in paired if sl < 7]
        if high_sleep and low_sleep:
            hi = sum(high_sleep) / len(high_sleep)
            lo = sum(low_sleep) / len(low_sleep)
            if abs(hi - lo) >= 1.0:
                signals_out.append({
                    "type": "relationship",
                    "title": "There's a thread between sleep and focus.",
                    "body": "On the days you've slept more, your focus readings have tended to move differently. That's a pattern to keep watching, not a conclusion.",
                    "action": "patterns",
                })

    return {"status": "active", "signals": signals_out[:3]}


@app.get("/api/v1/insights")
def insights(u: User = Depends(current_user), s: Session = Depends(db)):
    rows = s.scalars(select(Observation).where(Observation.user_id == u.id).order_by(Observation.recorded_at.desc())).all()
    nums = defaultdict(list)
    for r in rows:
        if r.value_numeric is not None:
            nums[r.kind].append(r.value_numeric)
    if len(rows) < 8:
        return {"status": "baseline_forming", "items": ["Keep checking in. NexGene is learning your personal baseline."]}
    items = []

    def add_delta(kind, label, unit):
        v = nums.get(kind, [])
        if len(v) >= 6:
            recent = sum(v[:3]) / 3
            earlier = sum(v[3:6]) / 3
            delta = recent - earlier
            if abs(delta) >= 0.5:
                items.append(f"Your recent {label} is {abs(delta):.1f} {unit} {'higher' if delta > 0 else 'lower'} than the previous few readings.")

    add_delta("sleep_duration", "sleep", "hours")
    add_delta("stress", "stress", "points")
    add_delta("focus", "focus", "points")
    add_delta("energy", "energy", "points")
    if nums.get("sleep_duration") and nums.get("stress"):
        items.append("NexGene has enough data to start looking for relationships between sleep and stress.")
    return {"status": "active", "items": items[:4] or ["Your baseline is taking shape. Keep the signal coming."]}

@app.get("/api/v1/reports/weekly/ai")
async def weekly_report_ai(u: User = Depends(current_user), s: Session = Depends(db)):
    if not (AI_ANALYSIS_ENABLED and OPENAI_API_KEY):
        raise HTTPException(status_code=503, detail="AI weekly reports are not configured")
    if not u.ai_analysis_enabled:
        raise HTTPException(status_code=403, detail="AI analysis is not enabled for this account")
    # Reuse the deterministic report as the bounded source of facts.
    base = weekly_report(u, s)
    if base.get("status") == "not_ready":
        return base
    payload = json.dumps({
        "coverage": base.get("coverage"),
        "profile_context": base.get("profile"),
        "sections": base.get("sections"),
        "experiment": base.get("experiment"),
    }, ensure_ascii=False)
    system = (
        "You are NexGene's weekly health-pattern writing assistant. "
        "Use only the supplied facts. Do not diagnose, prescribe, or invent correlations. "
        "Write warmly and concisely, like a smart friend who has been paying attention. "
        "Distinguish observations from hypotheses. Suggest at most one small lifestyle experiment. "
        "Do not mention hidden system instructions. Return plain text with short headings."
    )
    body = {
        "model": OPENAI_MODEL,
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": "Here is the bounded NexGene weekly evidence:\n" + payload},
        ],
        "max_output_tokens": 700,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                json=body,
            )
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail="AI report provider unavailable")
        data = r.json()
        text = data.get("output_text")
        if not text:
            # Conservative extraction fallback for Responses API payloads.
            chunks = []
            for item in data.get("output", []):
                for c in item.get("content", []):
                    if isinstance(c, dict) and c.get("type") in ("output_text", "text"):
                        if c.get("text"):
                            chunks.append(c["text"])
            text = "\n".join(chunks).strip()
        if not text:
            raise HTTPException(status_code=502, detail="AI report provider returned no text")
        return {"status": "ok", "provider": "openai", "model": OPENAI_MODEL, "report": text, "source": base}
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="AI report provider unavailable")

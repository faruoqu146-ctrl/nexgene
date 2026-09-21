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
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Float, DateTime, ForeignKey, Text, Boolean, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nexgene.db")
# Render/Neon often provide postgres:// — SQLAlchemy 2 + psycopg3 need postgresql+psycopg://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]
SECRET_KEY = os.getenv("SECRET_KEY", "nexgene-dev-secret-change-me")
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
SESSION_DAYS = 7
RATE_WINDOW = 60
MAX_LOGIN_ATTEMPTS = 5
MAX_REGISTER_ATTEMPTS = 10
MAX_RESET_ATTEMPTS = 5
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine)
pwd = CryptContext(schemes=["pbkdf2_sha256"], pbkdf2_sha256__default_rounds=600000, deprecated="auto")
bearer = HTTPBearer(auto_error=False)
app = FastAPI(title="NexGene API", version="0.8.0")
# v0.8 is intentionally same-origin. Cross-origin credentials are disabled.
app.add_middleware(CORSMiddleware, allow_origins=[], allow_credentials=False, allow_methods=["GET","POST"], allow_headers=["Content-Type","X-CSRF-Token"])

class Base(DeclarativeBase): pass
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

class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    value_numeric: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
Base.metadata.create_all(engine)
# Lightweight development migration for upgrading an existing v0.7.1 SQLite volume.
if DATABASE_URL.startswith("sqlite"):
    from sqlalchemy import inspect, text as sql_text
    insp=inspect(engine)
    cols={c["name"] for c in insp.get_columns("users")} if "users" in insp.get_table_names() else set()
    if "email_verified" not in cols:
        with engine.begin() as conn: conn.execute(sql_text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0"))

class AuthIn(BaseModel):
    email: str
    password: str = Field(min_length=12, max_length=128)

class ResetIn(BaseModel):
    email: str

class PasswordResetConfirm(BaseModel):
    token: str
    password: str = Field(min_length=12, max_length=128)
class CheckinIn(BaseModel):
    values: dict[str, float | str]

def db():
    s = SessionLocal()
    try: yield s
    finally: s.close()
def now(): return datetime.now(timezone.utc)
def ensure_aware(dt):
    if dt is None: return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
def hash_token(v: str): return hashlib.sha256(v.encode()).hexdigest()
def valid_password(p: str):
    return (len(p) >= 12 and any(c.islower() for c in p) and any(c.isupper() for c in p)
            and any(c.isdigit() for c in p) and any(not c.isalnum() for c in p))
def issue_session(u: User, s: Session):
    raw=secrets.token_urlsafe(48); csrf=secrets.token_urlsafe(32)
    s.add(SessionToken(user_id=u.id, token_hash=hash_token(raw), csrf_hash=hash_token(csrf), expires_at=now()+timedelta(days=SESSION_DAYS)))
    s.commit(); return raw, csrf
def get_session(request: Request, s: Session):
    raw=request.cookies.get("nexgene_session")
    if not raw: return None
    st=s.scalar(select(SessionToken).where(SessionToken.token_hash==hash_token(raw), SessionToken.revoked_at.is_(None)))
    if not st or ensure_aware(st.expires_at) < now(): return None
    return st
def require_csrf(request: Request, st: SessionToken):
    token=request.headers.get("X-CSRF-Token"); cookie=request.cookies.get("nexgene_csrf")
    if not token or not cookie or hash_token(token) != st.csrf_hash or token != cookie: raise HTTPException(403,"CSRF validation failed")
def current_user(request: Request, s: Session = Depends(db)):
    st=get_session(request,s)
    if not st: raise HTTPException(401,"Authentication required")
    return s.get(User,st.user_id)
def current_session(request: Request, s: Session = Depends(db)):
    st=get_session(request,s)
    if not st: raise HTTPException(401,"Authentication required")
    return st
RATE_BUCKETS=defaultdict(list)
def rate_limit(request: Request, key: str, limit: int):
    ip=request.client.host if request.client else "unknown"; bucket=f"{key}:{ip}"; now_ts=time.time()
    arr=RATE_BUCKETS[bucket]=[t for t in RATE_BUCKETS[bucket] if now_ts-t < RATE_WINDOW]
    if len(arr)>=limit: raise HTTPException(429,"Too many attempts. Please try again shortly.")
    arr.append(now_ts)
def password_policy_or_400(password: str):
    if not valid_password(password): raise HTTPException(400,"Password must be 12+ characters and include uppercase, lowercase, number, and symbol.")

@app.get("/api/v1/health")
def health(): return {"status":"ok","version":"0.8.0"}

# Serve the mobile app from the same origin so sign-in cannot fail because
# the browser is pointing at a different host/port than the API.
@app.get("/", include_in_schema=False)
def root(): return FileResponse("mobile/index.html")
app.mount("/static", StaticFiles(directory="mobile"), name="mobile")
@app.get("/api/v1/auth/csrf")
def csrf(request: Request, response: Response, s: Session=Depends(db)):
    st=get_session(request,s)
    if st:
        csrf_token=secrets.token_urlsafe(32)
        st.csrf_hash=hash_token(csrf_token)
        s.commit()
        response.set_cookie("nexgene_csrf", csrf_token, httponly=False, secure=COOKIE_SECURE, samesite="lax", path="/")
    return {"status":"ok"}

@app.post("/api/v1/auth/register")
def register(x: AuthIn, request: Request, response: Response, s: Session=Depends(db)):
    rate_limit(request,"register",MAX_REGISTER_ATTEMPTS); password_policy_or_400(x.password)
    email=x.email.strip().lower()
    if s.scalar(select(User).where(User.email==email)): raise HTTPException(409,"Unable to create account with those details.")
    u=User(email=email,password_hash=pwd.hash(x.password),email_verified=False); s.add(u); s.commit(); s.refresh(u)
    raw,csrf_token=issue_session(u,s); response.set_cookie("nexgene_session",raw,httponly=True,secure=COOKIE_SECURE,samesite="lax",max_age=SESSION_DAYS*86400,path="/"); response.set_cookie("nexgene_csrf",csrf_token,httponly=False,secure=COOKIE_SECURE,samesite="lax",max_age=SESSION_DAYS*86400,path="/")
    verify_raw=secrets.token_urlsafe(32); s.add(OneTimeToken(user_id=u.id,token_hash=hash_token(verify_raw),purpose="verify",expires_at=now()+timedelta(hours=24))); s.commit()
    out={"status":"created","email_verified":False}
    if DEV_MODE: out["dev_verification_token"]=verify_raw
    return out

@app.post("/api/v1/auth/login")
def login(x: AuthIn, request: Request, response: Response, s: Session=Depends(db)):
    rate_limit(request,"login",MAX_LOGIN_ATTEMPTS)
    u=s.scalar(select(User).where(User.email==x.email.strip().lower()))
    if not u or not pwd.verify(x.password,u.password_hash): raise HTTPException(401,"Invalid email or password")
    raw,csrf_token=issue_session(u,s); response.set_cookie("nexgene_session",raw,httponly=True,secure=COOKIE_SECURE,samesite="lax",max_age=SESSION_DAYS*86400,path="/"); response.set_cookie("nexgene_csrf",csrf_token,httponly=False,secure=COOKIE_SECURE,samesite="lax",max_age=SESSION_DAYS*86400,path="/")
    return {"status":"authenticated","email_verified":u.email_verified}

@app.post("/api/v1/auth/verify-email")
def verify_email(token: str, request: Request, response: Response, s: Session=Depends(db)):
    rate_limit(request,"verify",10); row=s.scalar(select(OneTimeToken).where(OneTimeToken.token_hash==hash_token(token),OneTimeToken.purpose=="verify",OneTimeToken.used_at.is_(None)))
    if not row or ensure_aware(row.expires_at)<now(): raise HTTPException(400,"Invalid or expired verification token")
    u=s.get(User,row.user_id); u.email_verified=True; row.used_at=now(); s.commit(); return {"status":"verified"}

@app.post("/api/v1/auth/logout")
def logout(request: Request, response: Response, st: SessionToken=Depends(current_session), s: Session=Depends(db)):
    require_csrf(request,st); st.revoked_at=now(); s.commit(); response.delete_cookie("nexgene_session",path="/"); response.delete_cookie("nexgene_csrf",path="/"); return {"status":"signed_out"}

@app.post("/api/v1/auth/password-reset/request")
def reset_request(x: ResetIn, request: Request, s: Session=Depends(db)):
    rate_limit(request,"reset",MAX_RESET_ATTEMPTS); u=s.scalar(select(User).where(User.email==x.email.strip().lower())); out={"status":"ok"}
    if u:
        raw=secrets.token_urlsafe(32); s.add(OneTimeToken(user_id=u.id,token_hash=hash_token(raw),purpose="reset",expires_at=now()+timedelta(minutes=30))); s.commit()
        if DEV_MODE: out["dev_reset_token"]=raw
    return out

@app.post("/api/v1/auth/password-reset/confirm")
def reset_confirm(x: PasswordResetConfirm, request: Request, response: Response, s: Session=Depends(db)):
    rate_limit(request,"reset_confirm",MAX_RESET_ATTEMPTS); password_policy_or_400(x.password)
    row=s.scalar(select(OneTimeToken).where(OneTimeToken.token_hash==hash_token(x.token),OneTimeToken.purpose=="reset",OneTimeToken.used_at.is_(None)))
    if not row or ensure_aware(row.expires_at)<now(): raise HTTPException(400,"Invalid or expired reset token")
    u=s.get(User,row.user_id); u.password_hash=pwd.hash(x.password); row.used_at=now(); s.query(SessionToken).filter(SessionToken.user_id==u.id,SessionToken.revoked_at.is_(None)).update({"revoked_at":now()}); s.commit(); response.delete_cookie("nexgene_session",path="/"); response.delete_cookie("nexgene_csrf",path="/"); return {"status":"password_reset"}

@app.get("/api/v1/auth/me")
def me(u:User=Depends(current_user)): return {"id":u.id,"email":u.email,"email_verified":u.email_verified}

def save_checkin(period,data,u,s):
    now=datetime.now(timezone.utc)
    for kind,value in data.values.items():
        s.add(Observation(user_id=u.id,kind=kind,value_numeric=float(value) if isinstance(value,(int,float)) else None,value_text=None if isinstance(value,(int,float)) else str(value),recorded_at=now))
    s.commit(); return {"saved":len(data.values),"period":period}
@app.post("/api/v1/checkins/morning")
def morning(data:CheckinIn,request:Request,u:User=Depends(current_user),st:SessionToken=Depends(current_session),s:Session=Depends(db)): require_csrf(request,st); return save_checkin("morning",data,u,s)
@app.post("/api/v1/checkins/evening")
def evening(data:CheckinIn,request:Request,u:User=Depends(current_user),st:SessionToken=Depends(current_session),s:Session=Depends(db)): require_csrf(request,st); return save_checkin("evening",data,u,s)
@app.get("/api/v1/today")
def today(u:User=Depends(current_user),s:Session=Depends(db)):
    since=datetime.now(timezone.utc)-timedelta(hours=24); rows=s.scalars(select(Observation).where(Observation.user_id==u.id,Observation.recorded_at>=since).order_by(Observation.recorded_at.desc())).all(); out={}
    for r in rows:
        if r.kind not in out: out[r.kind]=r.value_numeric if r.value_numeric is not None else r.value_text
    return out
@app.get("/api/v1/timeline")
def timeline(u:User=Depends(current_user),s:Session=Depends(db)):
    rows=s.scalars(select(Observation).where(Observation.user_id==u.id).order_by(Observation.recorded_at.desc()).limit(300)).all()
    return [{"kind":r.kind,"value":r.value_numeric if r.value_numeric is not None else r.value_text,"recorded_at":r.recorded_at.isoformat()} for r in rows]

@app.get("/api/v1/patterns")
def patterns(days:int=30,u:User=Depends(current_user),s:Session=Depends(db)):
    days=max(7,min(days,90)); since=datetime.now(timezone.utc)-timedelta(days=days)
    rows=s.scalars(select(Observation).where(Observation.user_id==u.id,Observation.recorded_at>=since).order_by(Observation.recorded_at.asc())).all()
    buckets=defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r.value_numeric is not None: buckets[r.recorded_at.date().isoformat()][r.kind].append(r.value_numeric)
    wanted=["sleep_duration","sleep_quality","energy","mood","stress","focus"]
    series=[]
    for day,vals in buckets.items():
        point={"date":day}
        for k in wanted:
            if vals.get(k): point[k]=round(sum(vals[k])/len(vals[k]),2)
        series.append(point)
    avgs={}
    for k in wanted:
        allv=[r.value_numeric for r in rows if r.kind==k and r.value_numeric is not None]
        if allv: avgs[k]=round(sum(allv)/len(allv),2)
    return {"days":days,"series":series,"averages":avgs,"observation_count":len(rows)}

@app.get("/api/v1/insights")
def insights(u:User=Depends(current_user),s:Session=Depends(db)):
    rows=s.scalars(select(Observation).where(Observation.user_id==u.id).order_by(Observation.recorded_at.desc())).all()
    nums=defaultdict(list)
    for r in rows:
        if r.value_numeric is not None: nums[r.kind].append(r.value_numeric)
    if len(rows)<8: return {"status":"baseline_forming","items":["Keep checking in. NexGene is learning your personal baseline."]}
    items=[]
    def add_delta(kind,label,unit):
        v=nums.get(kind,[])
        if len(v)>=6:
            recent=sum(v[:3])/3; earlier=sum(v[3:6])/3; delta=recent-earlier
            if abs(delta)>=0.5: items.append(f"Your recent {label} is {abs(delta):.1f} {unit} {'higher' if delta>0 else 'lower'} than the previous few readings.")
    add_delta("sleep_duration","sleep","hours")
    add_delta("stress","stress","points")
    add_delta("focus","focus","points")
    add_delta("energy","energy","points")
    if nums.get("sleep_duration") and nums.get("stress"):
        items.append("NexGene has enough data to start looking for relationships between sleep and stress.")
    return {"status":"active","items":items[:4] or ["Your baseline is taking shape. Keep the signal coming."]}

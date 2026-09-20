from datetime import datetime, timedelta, timezone
from typing import Optional
import os
from collections import defaultdict
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Float, DateTime, ForeignKey, Text, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nexgene.db")
SECRET_KEY = os.getenv("SECRET_KEY", "nexgene-dev-secret-change-me")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine)
pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)
app = FastAPI(title="NexGene API", version="0.7.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    value_numeric: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
Base.metadata.create_all(engine)

class AuthIn(BaseModel):
    email: str
    password: str = Field(min_length=8)
class CheckinIn(BaseModel):
    values: dict[str, float | str]

def db():
    s = SessionLocal()
    try: yield s
    finally: s.close()
def make_token(uid: int):
    return jwt.encode({"sub": str(uid), "exp": datetime.now(timezone.utc)+timedelta(days=7)}, SECRET_KEY, algorithm="HS256")
def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer), s: Session = Depends(db)):
    if not creds: raise HTTPException(401, "Authentication required")
    try: uid = int(jwt.decode(creds.credentials, SECRET_KEY, algorithms=["HS256"])["sub"])
    except Exception: raise HTTPException(401, "Invalid token")
    u=s.get(User,uid)
    if not u: raise HTTPException(401,"User not found")
    return u

@app.get("/api/v1/health")
def health(): return {"status":"ok","version":"0.7.1"}

# Serve the mobile app from the same origin so sign-in cannot fail because
# the browser is pointing at a different host/port than the API.
@app.get("/", include_in_schema=False)
def root(): return FileResponse("mobile/index.html")
app.mount("/static", StaticFiles(directory="mobile"), name="mobile")
@app.post("/api/v1/auth/register")
def register(x: AuthIn, s: Session=Depends(db)):
    email=x.email.strip().lower()
    if s.scalar(select(User).where(User.email==email)): raise HTTPException(409,"Email already registered")
    u=User(email=email,password_hash=pwd.hash(x.password)); s.add(u); s.commit(); s.refresh(u)
    return {"access_token":make_token(u.id),"token_type":"bearer"}
@app.post("/api/v1/auth/login")
def login(x: AuthIn,s:Session=Depends(db)):
    u=s.scalar(select(User).where(User.email==x.email.strip().lower()))
    if not u or not pwd.verify(x.password,u.password_hash): raise HTTPException(401,"Invalid email or password")
    return {"access_token":make_token(u.id),"token_type":"bearer"}
@app.get("/api/v1/auth/me")
def me(u:User=Depends(current_user)): return {"id":u.id,"email":u.email}

def save_checkin(period,data,u,s):
    now=datetime.now(timezone.utc)
    for kind,value in data.values.items():
        s.add(Observation(user_id=u.id,kind=kind,value_numeric=float(value) if isinstance(value,(int,float)) else None,value_text=None if isinstance(value,(int,float)) else str(value),recorded_at=now))
    s.commit(); return {"saved":len(data.values),"period":period}
@app.post("/api/v1/checkins/morning")
def morning(data:CheckinIn,u:User=Depends(current_user),s:Session=Depends(db)): return save_checkin("morning",data,u,s)
@app.post("/api/v1/checkins/evening")
def evening(data:CheckinIn,u:User=Depends(current_user),s:Session=Depends(db)): return save_checkin("evening",data,u,s)
@app.get("/api/v1/today")
def today(u:User=Depends(current_user),s:Session=Depends(db)):
    since=datetime.now(timezone.utc)-timedelta(hours=24); rows=s.scalars(select(Observation).where(Observation.user_id==u.id,Observation.recorded_at>=since).order_by(Observation.recorded_at.desc())).all(); out={}
    for r in rows: out.setdefault(r.kind,r.value_numeric if r.value_numeric is not None else r.value_text)
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

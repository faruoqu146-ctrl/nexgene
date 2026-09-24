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
MAX_LOGIN_ATTEMPTS = 100 if DEV_MODE else 5
MAX_REGISTER_ATTEMPTS = 100 if DEV_MODE else 10
MAX_RESET_ATTEMPTS = 50 if DEV_MODE else 5
MAX_VERIFY_ATTEMPTS = 50 if DEV_MODE else 10
MAX_CHECKIN_KEYS = 16
MAX_VALUE_LENGTH = 256
MAX_REQUEST_BYTES = 16 * 1024
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna").strip()
AI_ANALYSIS_ENABLED = os.getenv("AI_ANALYSIS_ENABLED", "false").lower() == "true"

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
pwd = CryptContext(
    schemes=["pbkdf2_sha256"],
    pbkdf2_sha256__default_rounds=600000,
    deprecated="auto",
)

DUMMY_PASSWORD_HASH = "$pbkdf2-sha256$600000$CkFoLSVkLCUE4Nx7D4GQsg$1aIBw7R/J2GBi/0x8iPtY.dLBs59VH0wxdQaUQyGKMc"

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

@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": APP_VERSION}

# NOTE: Full application restored in subsequent commit if truncated.
# See local tested version in artifacts.

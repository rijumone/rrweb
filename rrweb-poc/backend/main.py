import os
from typing import List, Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# -- Environment Variables --
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://rrweb_user:rrweb_password@localhost:5432/rrweb_db")
ADMIN_KEY = os.getenv("ADMIN_KEY", "secret-admin-key")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# -- Database Setup --
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class DbSession(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True, index=True)
    site_id = Column(String, index=True)
    domain = Column(String, index=True)
    user_agent = Column(String)
    path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    events = Column(JSON, default=[]) # We'll store events directly in JSONB array for simplicity in POC

# Create tables
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -- FastAPI App --
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Models --
class EventPayload(BaseModel):
    session_id: str
    domain: Optional[str] = None
    user_agent: Optional[str] = None
    path: Optional[str] = None
    events: List[Dict[str, Any]]

# -- Endpoints --

# 1. Ingest Endpoint (Called by Storefront)
@app.post("/events")
async def receive_events(
    payload: EventPayload, 
    x_site_id: str = Header(None), 
    db: Session = Depends(get_db)
):
    if not x_site_id:
        raise HTTPException(status_code=400, detail="X-Site-ID header is required")
        
    # Find or create session
    db_session = db.query(DbSession).filter(DbSession.id == payload.session_id).first()
    if not db_session:
        db_session = DbSession(
            id=payload.session_id,
            site_id=x_site_id,
            domain=payload.domain or "Unknown",
            user_agent=payload.user_agent or "Unknown",
            path=payload.path or "Unknown",
            events=[]
        )
        db.add(db_session)
    
    # Append new events
    existing_events = list(db_session.events)
    existing_events.extend(payload.events)
    db_session.events = existing_events
    
    db.commit()
    
    return {"status": "ok", "total_events": len(db_session.events)}


# 2. Admin Endpoint: List Sessions
@app.get("/sessions")
async def list_sessions(x_admin_key: str = Header(None), db: Session = Depends(get_db)):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    sessions = db.query(DbSession).order_by(DbSession.created_at.desc()).all()
    
    # Return summary data without the massive events payload
    return [
        {
            "id": s.id,
            "site_id": s.site_id,
            "domain": s.domain,
            "user_agent": s.user_agent,
            "path": s.path,
            "created_at": s.created_at.isoformat(),
            "event_count": len(s.events)
        }
        for s in sessions
    ]

# 3. Admin Endpoint: Get Events for a Session
@app.get("/events/{session_id}")
async def get_session_events(session_id: str, x_admin_key: str = Header(None), db: Session = Depends(get_db)):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    db_session = db.query(DbSession).filter(DbSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    return db_session.events

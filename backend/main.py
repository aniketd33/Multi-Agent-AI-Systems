"""
Main Entry Point - FinSight AI + Document Intelligence Agent
Multi-Agent AI System for Finance and Business Insights

Combines:
  - FinSight AI: user auth, JWT, research sessions, research documents (finsight.db)
  - Document Agent: document upload/listing/filtering/deletion (documents.db)
  - Frontend: static file serving + root route
"""

# ---------------------------------------------------------------------------
# Standard-library imports
# ---------------------------------------------------------------------------
from datetime import datetime, timedelta, timezone
import os
import secrets
import hashlib
import hmac
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Third-party imports
# ---------------------------------------------------------------------------
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    UploadFile,
    File,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import (
    create_engine,
    String,
    Boolean,
    DateTime,
    Integer,
    ForeignKey,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
    Session,
)

# ---------------------------------------------------------------------------
# Document Agent imports
# ---------------------------------------------------------------------------
from backend.api.documents import router as documents_router
from backend.database import initialize_database


# ===========================================================================
# FINSIGHT CONFIGURATION
# ===========================================================================

SECRET_KEY = os.getenv(
    "FINSIGHT_SECRET_KEY",
    "DEV_ONLY_CHANGE_THIS_SECRET_BEFORE_DEPLOYMENT"
)
ALGORITHM = "HS256"
TOKEN_MINUTES = 60

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./finsight.db")

# Maximum PDF upload size: 100 MB
MAX_UPLOAD_SIZE = 100 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024   # 1 MB chunks

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {}
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)


# ===========================================================================
# FINSIGHT DATABASE MODELS
# ===========================================================================

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )


class ResearchSession(Base):
    __tablename__ = "research_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )


class ResearchDocument(Base):
    __tablename__ = "research_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("research_sessions.id"), index=True, nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), default="application/pdf", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )


# Create only missing FinSight tables; existing records are preserved.
Base.metadata.create_all(engine)


# ===========================================================================
# FASTAPI APPLICATION
# ===========================================================================

FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "frontend"
)

app = FastAPI(
    title="FinSight AI + Document Intelligence Agent",
    description="Multi-Agent AI System for Finance and Business Insights",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# ---------------------------------------------------------------------------
# CORS — union of both origin lists
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://[::1]:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Document Agent router  (/api/documents/…)
# ---------------------------------------------------------------------------
app.include_router(documents_router)

# ---------------------------------------------------------------------------
# Static file serving for the FinSight frontend
# ---------------------------------------------------------------------------
if os.path.isdir(FRONTEND_DIR):
    app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")

# ---------------------------------------------------------------------------
# OAuth2 scheme (FinSight auth)
# ---------------------------------------------------------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


# ===========================================================================
# FINSIGHT REQUEST MODELS
# ===========================================================================

class RegisterBody(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


# ===========================================================================
# FINSIGHT DATABASE SESSION
# ===========================================================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ===========================================================================
# FINSIGHT PASSWORD SECURITY
# ===========================================================================

def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310000)
    return salt.hex() + "$" + digest.hex()


def verify_password(password, stored):
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), 310000
        )
        return hmac.compare_digest(actual, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


# ===========================================================================
# FINSIGHT JWT AUTHENTICATION
# ===========================================================================

def make_token(user_id):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=TOKEN_MINUTES)},
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    error = HTTPException(
        status_code=401,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", ""))
    except (JWTError, ValueError, TypeError):
        raise error
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise error
    return user


# ===========================================================================
# ROOT ROUTE — serves Document Agent frontend
# ===========================================================================

@app.get("/")
async def read_root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(
        status_code=404, content={"error": "Frontend not found"}
        )

# ---------------------------------------------------------------------------
# LOGIN ROUTE
# ---------------------------------------------------------------------------

@app.get("/login.html")
async def login_page():
    login_path = os.path.join(FRONTEND_DIR, "login.html")
    if os.path.exists(login_path):
        return FileResponse(login_path)
    return JSONResponse(
        status_code=404,
        content={"error": "Login page not found"}
    )

# ---------------------------------------------------------------------------
# REGISTER ROUTE
# ---------------------------------------------------------------------------

@app.get("/register.html")
async def register_page():
    register_path = os.path.join(FRONTEND_DIR, "register.html")
    if os.path.exists(register_path):
        return FileResponse(register_path)
    return JSONResponse(
        status_code=404,
        content={"error": "Register page not found"}
    )

# ===========================================================================
# HEALTH CHECK — single endpoint, merged information
# ===========================================================================

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "FinSight AI + Document Intelligence Agent",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "finsight_api": "online",
            "document_agent": "online"
        }
    }


# ===========================================================================
# API INFO
# ===========================================================================

@app.get("/api/info")
async def api_info():
    return {
        "name": "FinSight AI + Document Intelligence Agent",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "auth_register": "/auth/register",
            "auth_login": "/auth/login",
            "auth_me": "/auth/me",
            "research_sessions": "/research/sessions",
            "document_upload": "/api/documents/upload",
            "document_list": "/api/documents/",
            "document_detail": "/api/documents/{document_id}",
            "document_delete": "/api/documents/{document_id}",
        }
    }


# ===========================================================================
# FINSIGHT AUTH ROUTES
# ===========================================================================

@app.post("/auth/register", status_code=201)
def register(data: RegisterBody, db: Session = Depends(get_db)):
    email = str(data.email).lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(
        full_name=data.full_name.strip(),
        email=email,
        password_hash=hash_password(data.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Registration successful", "user": {"id": user.id, "full_name": user.full_name, "email": user.email}}


@app.post("/auth/login")
def login(data: LoginBody, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == str(data.email).lower().strip()).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account inactive")
    return {
        "access_token": make_token(user.id),
        "token_type": "bearer",
        "expires_in": TOKEN_MINUTES * 60,
        "user": {"id": user.id, "full_name": user.full_name, "email": user.email}
    }


@app.post("/auth/token")
def swagger_login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form_data.username.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account inactive")
    return {"access_token": make_token(user.id), "token_type": "bearer"}


@app.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "full_name": user.full_name, "email": user.email}


# ===========================================================================
# FINSIGHT PDF DOCUMENT INSPECTION
# ===========================================================================

@app.post("/documents/inspect")
async def inspect_pdf(file: UploadFile = File(...), user: User = Depends(current_user)):
    filename = file.filename or "uploaded_document.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files are supported")
    chunks = []
    total_size = 0
    while True:
        chunk = await file.read(UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="PDF exceeds the maximum upload limit of 100 MB.")
        chunks.append(chunk)
    raw = b"".join(chunks)
    if not raw.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Invalid PDF signature")
    try:
        import fitz
        doc = fitz.open(stream=raw, filetype="pdf")
        pages = len(doc)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
    except Exception:
        raise HTTPException(status_code=422, detail="PDF could not be parsed; it may be damaged or encrypted")
    finally:
        await file.close()
    return {
        "filename": filename,
        "pages": pages,
        "characters_extracted": len(text),
        "text_preview": text[:1200],
        "message": "Text extraction preview only; no AI analysis has run.",
        "uploaded_by": user.email
    }


# ===========================================================================
# FINSIGHT RESEARCH WORKSPACE
# ===========================================================================

STORAGE_BASE_PATH = Path(os.getenv(
    "STORAGE_BASE_PATH",
    str(Path(__file__).resolve().parent / "storage")
)).resolve()
MAX_RESEARCH_UPLOAD_SIZE = MAX_UPLOAD_SIZE
RESEARCH_CHUNK_SIZE = 64 * 1024


class ResearchSessionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class ResearchSessionUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


def _session_or_404(session_id: int, user: User, db: Session):
    item = db.query(ResearchSession).filter(
        ResearchSession.id == session_id,
        ResearchSession.owner_id == user.id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Research session not found")
    return item


def _document_response(doc: ResearchDocument):
    return {
        "id": doc.id,
        "session_id": doc.session_id,
        "filename": doc.original_filename,
        "stored_filename": doc.stored_filename,
        "content_type": doc.content_type,
        "size_bytes": doc.size_bytes,
        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None
    }


def _safe_storage_path(path_value: str) -> Path:
    candidate = Path(path_value).resolve()
    try:
        candidate.relative_to(STORAGE_BASE_PATH)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document storage path")
    return candidate


@app.post("/research/sessions", status_code=201)
def create_research_session(
    data: ResearchSessionCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Session name cannot be empty")
    item = ResearchSession(owner_id=user.id, name=name, description=data.description.strip())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {
        "id": item.id, "name": item.name, "description": item.description,
        "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(),
        "document_count": 0
    }


@app.get("/research/sessions")
def list_research_sessions(
    search: str = "",
    sort: str = "updated_desc",
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):
    query = db.query(ResearchSession).filter(ResearchSession.owner_id == user.id)
    term = search.strip()
    if term:
        query = query.filter(
            (ResearchSession.name.ilike(f"%{term}%")) |
            (ResearchSession.description.ilike(f"%{term}%"))
        )
    if sort == "name_asc":
        query = query.order_by(ResearchSession.name.asc())
    elif sort == "created_asc":
        query = query.order_by(ResearchSession.created_at.asc())
    elif sort == "created_desc":
        query = query.order_by(ResearchSession.created_at.desc())
    else:
        query = query.order_by(ResearchSession.updated_at.desc())
    items = query.all()
    return [{
        "id": item.id, "name": item.name, "description": item.description,
        "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(),
        "document_count": db.query(ResearchDocument).filter(ResearchDocument.session_id == item.id).count()
    } for item in items]


@app.get("/research/sessions/{session_id}")
def get_research_session(
    session_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):
    item = _session_or_404(session_id, user, db)
    docs = db.query(ResearchDocument).filter(
        ResearchDocument.session_id == item.id,
        ResearchDocument.owner_id == user.id
    ).order_by(ResearchDocument.uploaded_at.desc()).all()
    return {
        "id": item.id, "name": item.name, "description": item.description,
        "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(),
        "documents": [_document_response(doc) for doc in docs]
    }


@app.patch("/research/sessions/{session_id}")
def update_research_session(
    session_id: int,
    data: ResearchSessionUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):
    item = _session_or_404(session_id, user, db)
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Session name cannot be empty")
    item.name = name
    item.description = data.description.strip()
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return {
        "id": item.id, "name": item.name, "description": item.description,
        "updated_at": item.updated_at.isoformat()
    }


@app.delete("/research/sessions/{session_id}", status_code=204)
def delete_research_session(
    session_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):
    item = _session_or_404(session_id, user, db)
    docs = db.query(ResearchDocument).filter(
        ResearchDocument.session_id == item.id,
        ResearchDocument.owner_id == user.id
    ).all()
    paths = [doc.storage_path for doc in docs]
    try:
        for doc in docs:
            db.delete(doc)
        db.delete(item)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Research session deletion failed")
    for value in paths:
        try:
            path = _safe_storage_path(value)
            if path.is_file():
                path.unlink()
        except Exception as exc:
            print(f"Research storage cleanup warning: {exc}")
    return None


@app.post("/research/sessions/{session_id}/documents", status_code=201)
async def upload_research_document(
    session_id: int,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):
    item = _session_or_404(session_id, user, db)
    original = Path(file.filename or "document.pdf").name
    if not original.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files are supported")
    session_dir = (STORAGE_BASE_PATH / str(user.id) / str(item.id)).resolve()
    try:
        session_dir.relative_to(STORAGE_BASE_PATH)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid storage location")
    session_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}.pdf"
    temp_path = session_dir / f".{stored}.part"
    final_path = session_dir / stored
    total = 0
    signature = b""
    try:
        with temp_path.open("wb") as output:
            while True:
                chunk = await file.read(RESEARCH_CHUNK_SIZE)
                if not chunk:
                    break
                if not signature:
                    signature = chunk[:5]
                total += len(chunk)
                if total > MAX_RESEARCH_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail="PDF exceeds the maximum upload limit of 100 MB")
                output.write(chunk)
        if signature != b"%PDF-":
            raise HTTPException(status_code=400, detail="Invalid PDF signature")
        temp_path.replace(final_path)
        doc = ResearchDocument(
            session_id=item.id, owner_id=user.id, original_filename=original,
            stored_filename=stored, storage_path=str(final_path),
            content_type="application/pdf", size_bytes=total
        )
        db.add(doc)
        item.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(doc)
        return _document_response(doc)
    except HTTPException:
        db.rollback()
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        if final_path.exists():
            final_path.unlink(missing_ok=True)
        raise
    except Exception:
        db.rollback()
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        if final_path.exists():
            final_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Document upload failed")
    finally:
        await file.close()


@app.get("/research/sessions/{session_id}/documents")
def list_research_documents(
    session_id: int,
    search: str = "",
    sort: str = "uploaded_desc",
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):
    _session_or_404(session_id, user, db)
    query = db.query(ResearchDocument).filter(
        ResearchDocument.session_id == session_id,
        ResearchDocument.owner_id == user.id
    )
    if search.strip():
        query = query.filter(ResearchDocument.original_filename.ilike(f"%{search.strip()}%"))
    if sort == "name_asc":
        query = query.order_by(ResearchDocument.original_filename.asc())
    elif sort == "uploaded_asc":
        query = query.order_by(ResearchDocument.uploaded_at.asc())
    else:
        query = query.order_by(ResearchDocument.uploaded_at.desc())
    return [_document_response(doc) for doc in query.all()]


@app.get("/research/documents/{document_id}/download")
def download_research_document(
    document_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):
    doc = db.query(ResearchDocument).filter(
        ResearchDocument.id == document_id,
        ResearchDocument.owner_id == user.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    path = _safe_storage_path(doc.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored document file not found")
    return FileResponse(path, media_type="application/pdf", filename=doc.original_filename)


@app.delete("/research/documents/{document_id}", status_code=204)
def delete_research_document(
    document_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db)
):
    doc = db.query(ResearchDocument).filter(
        ResearchDocument.id == document_id,
        ResearchDocument.owner_id == user.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    stored_path = doc.storage_path
    try:
        db.delete(doc)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Document deletion failed")
    try:
        path = _safe_storage_path(stored_path)
        if path.is_file():
            path.unlink()
    except Exception as exc:
        print(f"Research document cleanup warning: {exc}")
    return None


# ===========================================================================
# STARTUP / SHUTDOWN EVENTS
# ===========================================================================

@app.on_event("startup")
async def startup_event():
    # Initialize Document Agent SQLite database (documents.db)
    # FinSight tables are already created above via Base.metadata.create_all(engine)
    db_ok = await initialize_database()
    status_str = "ok" if db_ok else "warning"
    print(f"[startup] Document Agent database: {status_str}")

    # Ensure upload directory exists
    uploads_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "uploads"
    )
    os.makedirs(uploads_dir, exist_ok=True)
    print(f"[startup] Uploads directory: {uploads_dir}")
    print("[startup] FinSight AI + Document Intelligence Agent ready")


@app.on_event("shutdown")
async def shutdown_event():
    print("[shutdown] Application stopped cleanly")


# ===========================================================================
# ERROR HANDLERS
# ===========================================================================

@app.exception_handler(404)
async def not_found_handler(request, exc):
    """
    Forward the endpoint-specific detail when an HTTPException(404) is raised
    (e.g. 'Document not found: <id>').  Fall back to a path-based message for
    genuine unmatched routes where Starlette supplies the generic 'Not Found'.
    """
    exc_detail = getattr(exc, "detail", None)
    if exc_detail and exc_detail != "Not Found":
        return JSONResponse(status_code=404, content={"detail": exc_detail})
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": f"The requested resource was not found: {request.url.path}",
            "timestamp": datetime.now().isoformat(),
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please try again later.",
            "timestamp": datetime.now().isoformat(),
        }
    )


# ===========================================================================
# DIRECT EXECUTION
# ===========================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")

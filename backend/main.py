
from datetime import datetime, timedelta, timezone
import os
import secrets
import hashlib
import hmac

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    UploadFile,
    File,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import create_engine, String, Boolean, DateTime, Integer
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
    Session,
)

# ---------------- CONFIGURATION ----------------

SECRET_KEY = os.getenv(
    "FINSIGHT_SECRET_KEY",
    "DEV_ONLY_CHANGE_THIS_SECRET_BEFORE_DEPLOYMENT"
)
ALGORITHM = "HS256"
TOKEN_MINUTES = 60

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./finsight.db")

# Maximum PDF upload size: 100 MB
MAX_UPLOAD_SIZE = 100 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB chunks

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


# ---------------- DATABASE ----------------

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )
    full_name: Mapped[str] = mapped_column(
        String(120), nullable=False
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )


Base.metadata.create_all(engine)


# ---------------- FASTAPI APP ----------------

app = FastAPI(
    title="FinSight AI API",
    version="0.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://[::1]:5500"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"]
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


# ---------------- REQUEST MODELS ----------------

class RegisterBody(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


# ---------------- DATABASE SESSION ----------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------- PASSWORD SECURITY ----------------

def hash_password(password):
    salt = secrets.token_bytes(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt,
        310000
    )

    return salt.hex() + "$" + digest.hex()


def verify_password(password, stored):
    try:
        salt_hex, digest_hex = stored.split("$", 1)

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            bytes.fromhex(salt_hex),
            310000
        )

        return hmac.compare_digest(
            actual,
            bytes.fromhex(digest_hex)
        )

    except (ValueError, TypeError):
        return False


# ---------------- JWT AUTHENTICATION ----------------

def make_token(user_id):
    now = datetime.now(timezone.utc)

    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=TOKEN_MINUTES)
        },
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
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = int(payload.get("sub", ""))

    except (JWTError, ValueError, TypeError):
        raise error

    user = db.get(User, user_id)

    if not user or not user.is_active:
        raise error

    return user


# ---------------- HEALTH CHECK ----------------

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "FinSight AI API"
    }


# ---------------- REGISTRATION ----------------

@app.post("/auth/register", status_code=201)
def register(
    data: RegisterBody,
    db: Session = Depends(get_db)
):
    email = str(data.email).lower().strip()

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists"
        )

    user = User(
        full_name=data.full_name.strip(),
        email=email,
        password_hash=hash_password(data.password)
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "message": "Registration successful",
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email
        }
    }


# ---------------- LOGIN ----------------

@app.post("/auth/login")
def login(
    data: LoginBody,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(
        User.email == str(data.email).lower().strip()
    ).first()

    if not user or not verify_password(
        data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Account inactive"
        )

    return {
        "access_token": make_token(user.id),
        "token_type": "bearer",
        "expires_in": TOKEN_MINUTES * 60,
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email
        }
    }


# ---------------- SWAGGER LOGIN ----------------

@app.post("/auth/token")
def swagger_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    email = form_data.username.lower().strip()

    user = db.query(User).filter(
        User.email == email
    ).first()

    if not user or not verify_password(
        form_data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Account inactive"
        )

    return {
        "access_token": make_token(user.id),
        "token_type": "bearer"
    }


# ---------------- CURRENT USER ----------------

@app.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email
    }


# ---------------- PDF DOCUMENT PROCESSING ----------------

@app.post("/documents/inspect")
async def inspect_pdf(
    file: UploadFile = File(...),
    user: User = Depends(current_user)
):
    filename = file.filename or "uploaded_document.pdf"

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=415,
            detail="Only PDF files are supported"
        )

    # Read in chunks and stop if the file exceeds 100 MB.
    chunks = []
    total_size = 0

    while True:
        chunk = await file.read(UPLOAD_CHUNK_SIZE)

        if not chunk:
            break

        total_size += len(chunk)

        if total_size > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail="PDF exceeds the maximum upload limit of 100 MB."
            )

        chunks.append(chunk)

    raw = b"".join(chunks)

    if not raw.startswith(b"%PDF"):
        raise HTTPException(
            status_code=400,
            detail="Invalid PDF signature"
        )

    try:
        import fitz

        doc = fitz.open(
            stream=raw,
            filetype="pdf"
        )

        pages = len(doc)
        text = "\n".join(
            page.get_text() for page in doc
        )

        doc.close()

    except Exception:
        raise HTTPException(
            status_code=422,
            detail="PDF could not be parsed; it may be damaged or encrypted"
        )

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

import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import User, UserProfile, Chapter, Question, Flashcard, UserProgress

# Security settings
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

app = FastAPI(title="SkyLearn API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Utils
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RegisterPayload(BaseModel):
    email: EmailStr
    password: str
    profile: UserProfile


class AnswerPayload(BaseModel):
    question_id: str
    user_answer: Optional[str] = None
    option_index: Optional[int] = None


class GenerateQuestionsPayload(BaseModel):
    chapter_id: str
    difficulty: str = "easy"
    count: int = 5


class TutorAskPayload(BaseModel):
    text: str
    context_chapter_id: Optional[str] = None


# Helpers

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict):
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = data.copy()
    to_encode.update({"exp": expire, "scope": "refresh_token"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db["user"].find_one({"email": email})
    if not user:
        raise credentials_exception
    return user


# Basic routes
@app.get("/")
def read_root():
    return {"message": "SkyLearn API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
        else:
            response["database"] = "❌ Not Available"
    except Exception as e:
        response["database"] = f"⚠️ Error: {str(e)[:80]}"
    return response


# Auth endpoints
@app.post("/api/auth/register", response_model=Token)
def register(payload: RegisterPayload):
    if db["user"].find_one({"email": payload.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    user_doc = User(
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        profile=payload.profile,
        roles=["student"],
        is_active=True,
    )
    create_document("user", user_doc)

    access = create_access_token({"sub": payload.email})
    refresh = create_refresh_token({"sub": payload.email})
    return Token(access_token=access, refresh_token=refresh, expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60)


@app.post("/api/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = db["user"].find_one({"email": form_data.username})
    if not user:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    if not verify_password(form_data.password, user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    access = create_access_token({"sub": user["email"]})
    refresh = create_refresh_token({"sub": user["email"]})
    return Token(access_token=access, refresh_token=refresh, expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60)


@app.get("/api/auth/me")
def me(current_user=Depends(get_current_user)):
    current_user["id"] = str(current_user.get("_id"))
    # Remove sensitive fields
    current_user.pop("password_hash", None)
    return current_user


# Chapters
@app.get("/api/chapters")
def list_chapters(subject: Optional[str] = None, class_number: Optional[int] = None, search: Optional[str] = None):
    query = {}
    if subject:
        query["subject"] = {"$regex": f"^{subject}$", "$options": "i"}
    if class_number:
        query["class_number"] = class_number
    if search:
        query["title"] = {"$regex": search, "$options": "i"}

    items = get_documents("chapter", query, limit=100)
    # Map ObjectIds to string
    for it in items:
        it["id"] = str(it.get("_id"))
    return items


@app.get("/api/chapters/{chapter_id}")
def get_chapter(chapter_id: str):
    try:
        doc = db["chapter"].find_one({"_id": ObjectId(chapter_id)})
    except Exception:
        raise HTTPException(404, detail="Invalid chapter id")
    if not doc:
        raise HTTPException(404, detail="Chapter not found")
    doc["id"] = str(doc.get("_id"))
    return doc


@app.get("/api/chapters/{chapter_id}/concepts")
def get_chapter_concepts(chapter_id: str):
    chap = get_chapter(chapter_id)
    return chap.get("concepts", [])


# Questions
@app.post("/api/questions/generate")
def generate_questions(payload: GenerateQuestionsPayload):
    # Simple stub generation; replace with LangChain later
    try:
        _ = get_chapter(payload.chapter_id)
    except HTTPException:
        raise

    generated = []
    for i in range(max(1, min(payload.count, 20))):
        qdoc = Question(
            chapter_id=payload.chapter_id,
            difficulty=payload.difficulty if payload.difficulty in ["easy", "medium", "hard"] else "easy",
            type="mcq",
            content={"prompt": f"Auto-generated Q{i+1}: What is the key idea of this section?", "options": [
                "Definition A", "Definition B", "Definition C", "Definition D"
            ]},
            answer={"correct_option": 1},
            explanation="Review the chapter summary and key formulas.",
            vetted=False,
        )
        inserted_id = create_document("question", qdoc)
        item = db["question"].find_one({"_id": ObjectId(inserted_id)})
        item["id"] = str(item["_id"]) 
        generated.append(item)
    return {"items": generated}


@app.get("/api/questions/{qid}")
def get_question(qid: str):
    try:
        doc = db["question"].find_one({"_id": ObjectId(qid)})
    except Exception:
        raise HTTPException(404, detail="Invalid question id")
    if not doc:
        raise HTTPException(404, detail="Question not found")
    doc["id"] = str(doc["_id"])
    return doc


@app.post("/api/questions/answer")
def answer_question(payload: AnswerPayload):
    q = get_question(payload.question_id)
    correct = False
    if q.get("type") == "mcq":
        correct = (payload.option_index is not None and payload.option_index == q.get("answer", {}).get("correct_option"))
    elif q.get("type") == "short":
        ua = (payload.user_answer or "").strip().lower()
        ca = (q.get("answer", {}).get("text") or "").strip().lower()
        correct = ua == ca
    return {"correct": bool(correct), "explanation": q.get("explanation", "")}


# Tutor (stubbed)
@app.post("/api/tutor/ask")
def tutor_ask(payload: TutorAskPayload, current_user=Depends(get_current_user)):
    context_snippet = ""
    if payload.context_chapter_id:
        try:
            chap = get_chapter(payload.context_chapter_id)
            context_snippet = (chap.get("ncert_content") or "")[:300]
        except HTTPException:
            context_snippet = ""
    answer = (
        "Here's a concise explanation: "
        + ("Based on your chapter context: " + context_snippet if context_snippet else "")
        + " | " + payload.text
    )[:800]
    # Persist history
    doc = {
        "user_id": str(current_user.get("_id")),
        "text": payload.text,
        "answer": answer,
        "chapter_id": payload.context_chapter_id,
        "created_at": datetime.now(timezone.utc),
    }
    inserted_id = db["tutorhistory"].insert_one(doc).inserted_id
    doc["id"] = str(inserted_id)
    return doc


@app.get("/api/tutor/history")
def tutor_history(current_user=Depends(get_current_user)):
    items = list(db["tutorhistory"].find({"user_id": str(current_user.get("_id"))}).sort("created_at", -1).limit(50))
    for it in items:
        it["id"] = str(it.get("_id"))
    return items


# Flashcards (basic)
@app.get("/api/flashcards")
def list_flashcards(current_user=Depends(get_current_user), due: Optional[bool] = False):
    query = {"user_id": str(current_user.get("_id"))}
    now = datetime.now(timezone.utc)
    if due:
        query["due_at"] = {"$lte": now}
    items = list(db["flashcard"].find(query).limit(100))
    for it in items:
        it["id"] = str(it.get("_id"))
    return items


class GenerateFlashcardsPayload(BaseModel):
    chapter_id: str
    count: int = 5


@app.post("/api/flashcards/generate")
def generate_flashcards(payload: GenerateFlashcardsPayload, current_user=Depends(get_current_user)):
    # Simple stubbed generation from chapter content
    chap = get_chapter(payload.chapter_id)
    stem = (chap.get("title") or "Chapter").split(" ")[0]
    docs = []
    now = datetime.now(timezone.utc)
    for i in range(max(1, min(payload.count, 20))):
        doc = {
            "user_id": str(current_user.get("_id")),
            "front": f"What is {stem} concept {i+1}?",
            "back": f"Explanation for {stem} concept {i+1}.",
            "blooms_level": "remember",
            "due_at": now + timedelta(days=i % 3 + 1),
            "created_at": now,
        }
        docs.append(doc)
    if docs:
        db["flashcard"].insert_many(docs)
    for d in docs:
        d["id"] = str(d.get("_id", ""))
    return {"items": docs}


class ReviewPayload(BaseModel):
    grade: int


@app.put("/api/flashcards/{fid}/review")
def review_flashcard(fid: str, payload: ReviewPayload, current_user=Depends(get_current_user)):
    try:
        oid = ObjectId(fid)
    except Exception:
        raise HTTPException(404, detail="Invalid flashcard id")
    doc = db["flashcard"].find_one({"_id": oid, "user_id": str(current_user.get("_id"))})
    if not doc:
        raise HTTPException(404, detail="Flashcard not found")
    # naive spacing: higher grade -> longer next interval
    days = max(1, min(7, payload.grade))
    next_due = datetime.now(timezone.utc) + timedelta(days=days)
    db["flashcard"].update_one({"_id": oid}, {"$set": {"due_at": next_due, "updated_at": datetime.now(timezone.utc)}})
    return {"next_due_at": next_due}


# Expose schemas for viewer/tools
@app.get("/schema")
def schema_introspect():
    return {
        "collections": [
            "user", "chapter", "question", "userprogress", "flashcard", "tutorhistory"
        ]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

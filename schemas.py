"""
Database Schemas for SkyLearn MVP (MongoDB)

Each Pydantic model represents a collection in your database.
Collection name is the lowercase of the class name.

Examples:
- User -> "user"
- Chapter -> "chapter"
- Question -> "question"
- UserProgress -> "userprogress"
- Flashcard -> "flashcard"
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Any


class UserProfile(BaseModel):
    exam_type: Literal['NEET', 'NSEJS', 'Board']
    grade: Literal[11, 12]
    subjects: List[str] = []
    learning_goals: List[str] = []


class User(BaseModel):
    email: str = Field(..., description="Email address")
    password_hash: str = Field(..., description="BCrypt hash of password")
    profile: UserProfile
    roles: List[str] = ["student"]
    is_active: bool = True


class ChapterConcept(BaseModel):
    id: str
    name: str
    summary: Optional[str] = None
    links: List[str] = []


class Chapter(BaseModel):
    subject: str
    class_number: int = Field(..., ge=1, le=12, description="Class/Grade number")
    title: str
    ncert_content: Optional[str] = None
    concepts: List[ChapterConcept] = []
    prerequisites: List[str] = []  # store as string ObjectIds or external refs


class QuestionContent(BaseModel):
    prompt: str
    options: Optional[List[str]] = None


class QuestionAnswer(BaseModel):
    correct_option: Optional[int] = None  # index of correct option for MCQ
    text: Optional[str] = None            # free-form answer for descriptive


class Question(BaseModel):
    chapter_id: str
    difficulty: Literal['easy', 'medium', 'hard']
    type: Literal['mcq', 'short', 'true_false']
    content: QuestionContent
    answer: QuestionAnswer
    explanation: Optional[str] = None
    pyq_source: Optional[str] = None
    vetted: bool = False


class UserProgress(BaseModel):
    user_id: str
    chapter_id: str
    quiz_scores: List[Any] = []
    revision_schedule: List[Any] = []
    weak_areas: List[str] = []


class Flashcard(BaseModel):
    user_id: str
    front: str
    back: str
    blooms_level: Optional[Literal['remember', 'understand', 'apply', 'analyze', 'evaluate', 'create']] = None
    due_at: Optional[str] = None  # ISO string

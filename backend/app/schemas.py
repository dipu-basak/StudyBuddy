from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field

# ── Authentication Schemas ──────────────────────────────────────────

class SignupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=50, description="Full name")
    email: EmailStr = Field(..., description="Valid email address")
    password: str = Field(..., min_length=6, description="Password with minimum 6 characters")

class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="Registered email address")
    password: str = Field(..., description="Account password")

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    plan: str = "free"
    streak: int = 0
    xp: int = 0
    level: int = 1
    total_uploads: int = 0
    best_quiz_score: float = 0.0
    badges: List[str] = Field(default_factory=list)
    requests_today: int = 0
    avatar: Optional[str] = None
    created_at: Optional[str] = None

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    message: str = "Authentication successful"


# ── File Upload & Validation Schemas ────────────────────────────────

class FileValidationResult(BaseModel):
    """Result returned by file security verification."""
    is_valid: bool
    detected_type: Optional[str] = None  # "pdf", "image", "text"
    mime_type: Optional[str] = None
    error_message: Optional[str] = None

class FileUploadResponse(BaseModel):
    """Response returned upon successful safe file upload."""
    file_id: str
    filename: str
    original_filename: str
    file_type: str  # "pdf", "image", "text"
    mime_type: str
    file_size: int
    file_size_formatted: str
    sha256_hash: str
    uploaded_at: str
    message: str = "File uploaded and verified successfully"

class DocumentMetadataResponse(BaseModel):
    """Metadata for a stored user document."""
    file_id: str
    user_id: str
    original_filename: str
    file_type: str
    mime_type: str
    file_size: int
    file_size_formatted: str
    sha256_hash: str
    uploaded_at: str
    status: str = "ready"

class UserDocumentListResponse(BaseModel):
    """List of documents owned by the authenticated student."""
    documents: List[DocumentMetadataResponse]
    total: int

class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    error_code: Optional[str] = None


# ── Gemini AI Structured Output & Study Session Schemas ─────────────

class QuizQuestion(BaseModel):
    question: str = Field(..., description="The multiple choice question text")
    options: List[str] = Field(..., min_length=4, max_length=4, description="List of exactly 4 answer options")
    correct_answer_index: int = Field(..., ge=0, le=3, description="0-based index of the correct answer (0, 1, 2, or 3)")
    explanation: str = Field(..., description="Concise explanation for why the answer is correct")

class SummarySection(BaseModel):
    title: str = Field(..., description="Section title or core concept heading")
    bullet_points: List[str] = Field(..., description="High-yield takeaways and bullet points")

class StudySummary(BaseModel):
    topic: str = Field(..., description="Subject or exam topic")
    overview: str = Field(..., description="Executive summary of the lecture material")
    key_concepts: List[SummarySection] = Field(..., description="Key concept breakdowns")
    formulas_and_definitions: List[str] = Field(default_factory=list, description="Essential formulas, terms, and definitions")
    high_yield_exam_tips: List[str] = Field(default_factory=list, description="Common exam traps and high-yield tips")

class ExamPrepContent(BaseModel):
    """Full structured output expected from Gemini AI."""
    topic: str = Field(..., description="Subject or chapter topic")
    summary: StudySummary = Field(..., description="30-minute high-yield summary")
    quiz: List[QuizQuestion] = Field(..., description="5-minute timed quiz questions")

class GenerateSessionRequest(BaseModel):
    file_id: Optional[str] = Field(None, description="ID of previously uploaded document")
    notes_text: Optional[str] = Field(None, description="Pasted lecture notes or transcript")
    topic: Optional[str] = Field(None, description="Optional topic or exam title override")
    mode: str = Field("both", description="Generation mode: 'summary', 'quiz', or 'both'")

class GenerateSessionResponse(BaseModel):
    session_id: str
    file_id: Optional[str] = None
    topic: str
    mode: str
    summary: StudySummary
    quiz: List[QuizQuestion]
    created_at: str
    message: str = "Study session generated successfully!"

class QuizAnswerSubmission(BaseModel):
    question_index: int
    selected_option_index: int

class QuizSubmitRequest(BaseModel):
    session_id: str
    answers: List[QuizAnswerSubmission]
    time_taken_seconds: int = 0

class QuestionReviewDetail(BaseModel):
    question_index: int
    question: str
    options: List[str]
    selected_option_index: int
    correct_answer_index: int
    is_correct: bool
    explanation: str

class QuizResultResponse(BaseModel):
    session_id: str
    score_percent: float
    correct_count: int
    total_questions: int
    xp_earned: int
    details: List[QuestionReviewDetail]
    message: str

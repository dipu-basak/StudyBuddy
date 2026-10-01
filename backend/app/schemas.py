from datetime import datetime
from typing import Optional, List
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

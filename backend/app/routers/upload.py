import hashlib
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional

# Path resolution for standalone or package execution
_current_dir = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.path.dirname(_current_dir)
_backend_dir = os.path.dirname(_app_dir)
for _path in [_backend_dir, _app_dir, _current_dir]:
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from app.config import settings
    from app.database import get_documents_collection, get_users_collection
    from app.file_security import detect_and_validate_file, sanitize_filename
    from app.routers.auth import get_current_user
    from app.schemas import (
        DocumentMetadataResponse,
        FileUploadResponse,
        UserDocumentListResponse,
    )
except ImportError:
    from config import settings
    from database import get_documents_collection, get_users_collection
    from file_security import detect_and_validate_file, sanitize_filename
    from routers.auth import get_current_user
    from schemas import (
        DocumentMetadataResponse,
        FileUploadResponse,
        UserDocumentListResponse,
    )

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

router = APIRouter(prefix="/api/upload", tags=["File Uploads"])

def format_file_size(size_bytes: int) -> str:
    """Format bytes into human-readable file size string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{round(size_bytes / 1024, 1)} KB"
    else:
        return f"{round(size_bytes / (1024 * 1024), 2)} MB"


@router.post("", response_model=FileUploadResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=FileUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Securely uploads a lecture slide, note document, or diagram photo.
    Performs multi-layered security validation to ensure no malicious files can be uploaded:
    - Path traversal & filename sanitization
    - Whitelist extension check
    - Double extension detection
    - Binary executable header & magic byte scanning
    - PDF exploit scanning (disallows /Launch actions and embedded executables)
    - Image script injection scanning (disallows PHP/script injections)
    - Plain text UTF-8 & script command checks
    - File size limits (max 20MB)
    """
    raw_filename = file.filename or "uploaded_document"
    clean_filename = sanitize_filename(raw_filename)

    # 1. Read file with chunked size guard (DoS / size bomb protection)
    chunk_size = 64 * 1024  # 64 KB
    content_chunks = []
    total_bytes = 0

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > settings.MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB}MB.",
            )
        content_chunks.append(chunk)

    file_bytes = b"".join(content_chunks)

    # 2. Comprehensive Security & Malicious Payload Inspection
    validation = detect_and_validate_file(file_bytes, clean_filename)
    if not validation.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=validation.error_message or "Security check failed: Invalid or malicious file format.",
        )

    # 3. Calculate cryptographic SHA-256 integrity hash
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()

    # 4. Generate unguessable, secure storage filename
    file_id = str(uuid.uuid4())
    _, ext = os.path.splitext(clean_filename)
    stored_filename = f"{file_id}_{sha256_hash[:8]}{ext.lower()}"
    storage_abs_path = os.path.join(settings.UPLOAD_DIR, stored_filename)

    # 5. Persist file bytes to designated uploads directory
    try:
        with open(storage_abs_path, "wb") as f:
            f.write(file_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to securely store file: {str(e)}",
        )

    # 6. Record metadata in documents database
    now_iso = datetime.now(timezone.utc).isoformat()
    doc_record = {
        "file_id": file_id,
        "user_id": str(current_user["_id"]),
        "original_filename": clean_filename,
        "stored_filename": stored_filename,
        "file_type": validation.detected_type,
        "mime_type": validation.mime_type,
        "file_size": total_bytes,
        "sha256_hash": sha256_hash,
        "storage_path": os.path.relpath(storage_abs_path, _backend_dir),
        "uploaded_at": now_iso,
        "status": "ready",
    }

    docs_col = get_documents_collection()
    await docs_col.insert_one(doc_record)

    # 7. Increment user's total_uploads counter
    users_col = get_users_collection()
    await users_col.update_one(
        {"_id": str(current_user["_id"])},
        {"$inc": {"total_uploads": 1}},
    )

    size_formatted = format_file_size(total_bytes)

    return FileUploadResponse(
        file_id=file_id,
        filename=stored_filename,
        original_filename=clean_filename,
        file_type=validation.detected_type or "document",
        mime_type=validation.mime_type or "application/octet-stream",
        file_size=total_bytes,
        file_size_formatted=size_formatted,
        sha256_hash=sha256_hash,
        uploaded_at=now_iso,
        message=f"'{clean_filename}' ({size_formatted}) verified and uploaded successfully!",
    )


@router.get("/documents", response_model=UserDocumentListResponse)
async def list_user_documents(current_user: dict = Depends(get_current_user)):
    """Fetch all lecture documents uploaded by the authenticated student."""
    docs_col = get_documents_collection()
    user_id = str(current_user["_id"])

    if hasattr(docs_col, "find") and callable(docs_col.find):
        raw_docs = await docs_col.find({"user_id": user_id})
    else:
        cursor = docs_col.find({"user_id": user_id})
        raw_docs = await cursor.to_list(length=100)

    documents = []
    for d in raw_docs:
        size_bytes = d.get("file_size", 0)
        documents.append(
            DocumentMetadataResponse(
                file_id=str(d.get("file_id")),
                user_id=str(d.get("user_id")),
                original_filename=d.get("original_filename", "unnamed_document"),
                file_type=d.get("file_type", "document"),
                mime_type=d.get("mime_type", "application/octet-stream"),
                file_size=size_bytes,
                file_size_formatted=format_file_size(size_bytes),
                sha256_hash=d.get("sha256_hash", ""),
                uploaded_at=str(d.get("uploaded_at")),
                status=d.get("status", "ready"),
            )
        )

    return UserDocumentListResponse(
        documents=documents,
        total=len(documents),
    )


@router.get("/documents/{file_id}", response_model=DocumentMetadataResponse)
async def get_document_details(
    file_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Retrieve metadata for a specific uploaded lecture document."""
    docs_col = get_documents_collection()
    doc = await docs_col.find_one({"file_id": file_id, "user_id": str(current_user["_id"])})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or you do not have permission to view it.",
        )

    size_bytes = doc.get("file_size", 0)
    return DocumentMetadataResponse(
        file_id=str(doc.get("file_id")),
        user_id=str(doc.get("user_id")),
        original_filename=doc.get("original_filename", "unnamed_document"),
        file_type=doc.get("file_type", "document"),
        mime_type=doc.get("mime_type", "application/octet-stream"),
        file_size=size_bytes,
        file_size_formatted=format_file_size(size_bytes),
        sha256_hash=doc.get("sha256_hash", ""),
        uploaded_at=str(doc.get("uploaded_at")),
        status=doc.get("status", "ready"),
    )

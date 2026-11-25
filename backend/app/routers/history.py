import logging
import os
import sys
from typing import Optional

# Path resolution for standalone or package execution
_current_dir = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.path.dirname(_current_dir)
_backend_dir = os.path.dirname(_app_dir)
for _path in [_backend_dir, _app_dir, _current_dir]:
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from app.database import get_documents_collection, get_sessions_collection
    from app.routers.auth import get_current_user
    from app.schemas import (
        HistoryDeleteResponse,
        HistoryItemResponse,
        HistoryListResponse,
        QuizQuestion,
        StudySummary,
    )
except ImportError:
    from database import get_documents_collection, get_sessions_collection
    from routers.auth import get_current_user
    from schemas import (
        HistoryDeleteResponse,
        HistoryItemResponse,
        HistoryListResponse,
        QuizQuestion,
        StudySummary,
    )

from fastapi import APIRouter, Depends, HTTPException, status

logger = logging.getLogger("history_router")
router = APIRouter(prefix="/api/history", tags=["Study History"])


@router.get("", response_model=HistoryListResponse, status_code=status.HTTP_200_OK)
@router.get("/", response_model=HistoryListResponse, status_code=status.HTTP_200_OK)
async def list_user_history(current_user: dict = Depends(get_current_user)):
    """
    Fetches all previously generated study materials for the authenticated student.
    Returns records sorted newest first. Only records belonging to the current user are returned.
    """
    user_id = str(current_user["_id"])
    sessions_col = get_sessions_collection()

    query = {"user_id": user_id}
    res = sessions_col.find(query)

    # Support both Motor AsyncIOMotorCursor and LocalJsonMongoCollection coroutine
    if hasattr(res, "sort"):
        cursor = res.sort("created_at", -1)
        raw_items = await cursor.to_list(length=200)
    else:
        raw_items = await res
        raw_items.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    history_items = []
    for item in raw_items:
        h_id = item.get("history_id") or item.get("session_id", "")
        s_id = item.get("session_id") or h_id
        fn = item.get("original_filename") or f"{item.get('topic', 'Lecture Notes')}.txt"
        
        # Ensure summary is parsed robustly even with legacy or mega-quiz schemas
        summary_raw = item.get("summary", {})
        if isinstance(summary_raw, dict):
            summary_dict = dict(summary_raw)
            if "topic" not in summary_dict:
                summary_dict["topic"] = item.get("topic", "Study Session")
            if "high_yield_exam_tips" not in summary_dict and "exam_tips" in summary_dict:
                summary_dict["high_yield_exam_tips"] = summary_dict.get("exam_tips", [])
            try:
                summary_obj = StudySummary(**summary_dict)
            except Exception:
                summary_obj = StudySummary(
                    topic=summary_dict.get("topic") or item.get("topic", "Study Session"),
                    overview=summary_dict.get("overview", ""),
                    key_concepts=[],
                    formulas_and_definitions=summary_dict.get("formulas_and_definitions", []),
                    high_yield_exam_tips=summary_dict.get("high_yield_exam_tips", []),
                )
        else:
            summary_obj = StudySummary(topic=item.get("topic", "Study Session"), overview=str(summary_raw or ""))
        
        quiz_raw = item.get("quiz", [])
        quiz_objs = [QuizQuestion(**q) if isinstance(q, dict) else q for q in quiz_raw]

        history_items.append(
            HistoryItemResponse(
                history_id=h_id,
                session_id=s_id,
                user_id=str(item.get("user_id")),
                original_filename=fn,
                topic=item.get("topic", "Study Session"),
                mode=item.get("mode", "both"),
                summary=summary_obj,
                quiz=quiz_objs,
                created_at=item.get("created_at", ""),
                file_id=item.get("file_id"),
            )
        )

    return HistoryListResponse(
        history=history_items,
        total=len(history_items),
        message="History retrieved successfully",
    )


@router.get("/{history_id}", response_model=HistoryItemResponse, status_code=status.HTTP_200_OK)
async def get_history_item(
    history_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Retrieves a single study history record by its history_id or session_id.
    Strictly verifies ownership: users can only access their own history.
    """
    user_id = str(current_user["_id"])
    sessions_col = get_sessions_collection()

    record = await sessions_col.find_one({
        "$or": [{"history_id": history_id}, {"session_id": history_id}],
        "user_id": user_id,
    })
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="History record not found or you do not have permission to view it.",
        )

    h_id = record.get("history_id") or record.get("session_id", "")
    s_id = record.get("session_id") or h_id
    fn = record.get("original_filename") or f"{record.get('topic', 'Lecture Notes')}.txt"

    summary_raw = record.get("summary", {})
    if isinstance(summary_raw, dict):
        summary_dict = dict(summary_raw)
        if "topic" not in summary_dict:
            summary_dict["topic"] = record.get("topic", "Study Session")
        if "high_yield_exam_tips" not in summary_dict and "exam_tips" in summary_dict:
            summary_dict["high_yield_exam_tips"] = summary_dict.get("exam_tips", [])
        try:
            summary_obj = StudySummary(**summary_dict)
        except Exception:
            summary_obj = StudySummary(
                topic=summary_dict.get("topic") or record.get("topic", "Study Session"),
                overview=summary_dict.get("overview", ""),
                key_concepts=[],
                formulas_and_definitions=summary_dict.get("formulas_and_definitions", []),
                high_yield_exam_tips=summary_dict.get("high_yield_exam_tips", []),
            )
    else:
        summary_obj = StudySummary(topic=record.get("topic", "Study Session"), overview=str(summary_raw or ""))
    quiz_raw = record.get("quiz", [])
    quiz_objs = [QuizQuestion(**q) if isinstance(q, dict) else q for q in quiz_raw]

    return HistoryItemResponse(
        history_id=h_id,
        session_id=s_id,
        user_id=str(record.get("user_id")),
        original_filename=fn,
        topic=record.get("topic", "Study Session"),
        mode=record.get("mode", "both"),
        summary=summary_obj,
        quiz=quiz_objs,
        created_at=record.get("created_at", ""),
        file_id=record.get("file_id"),
    )


@router.delete("/{history_id}", response_model=HistoryDeleteResponse, status_code=status.HTTP_200_OK)
async def delete_history_item(
    history_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Deletes an individual history record for the authenticated user.
    Ensures that each student can delete only their own records.
    """
    user_id = str(current_user["_id"])
    sessions_col = get_sessions_collection()

    # Verify existence and ownership
    query = {
        "$or": [{"history_id": history_id}, {"session_id": history_id}],
        "user_id": user_id,
    }
    record = await sessions_col.find_one(query)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="History record not found or you do not have permission to delete it.",
        )

    # Delete record from database
    await sessions_col.delete_one(query)

    # Optional: cleanup any lingering document reference
    if record.get("file_id"):
        try:
            docs_col = get_documents_collection()
            await docs_col.delete_many({"file_id": record.get("file_id"), "user_id": user_id})
        except Exception as e:
            logger.warning(f"Could not delete linked document metadata: {e}")

    logger.info(f"User '{user_id}' deleted history record '{history_id}'.")
    return HistoryDeleteResponse(
        history_id=history_id,
        message="History record deleted successfully.",
    )

import json
import logging
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
    from app.database import (
        get_documents_collection,
        get_sessions_collection,
        get_users_collection,
    )
    from app.routers.auth import get_current_user
    from app.schemas import (
        ExamPrepContent,
        GenerateSessionRequest,
        GenerateSessionResponse,
        MegaQuizCreateRequest,
        MegaQuizResponse,
        QuestionReviewDetail,
        QuizQuestion,
        QuizResultResponse,
        QuizSubmitRequest,
        StudySummary,
    )
except ImportError:
    from config import settings
    from database import (
        get_documents_collection,
        get_sessions_collection,
        get_users_collection,
    )
    from routers.auth import get_current_user
    from schemas import (
        ExamPrepContent,
        GenerateSessionRequest,
        GenerateSessionResponse,
        MegaQuizCreateRequest,
        MegaQuizResponse,
        QuestionReviewDetail,
        QuizQuestion,
        QuizResultResponse,
        QuizSubmitRequest,
        StudySummary,
    )

from fastapi import APIRouter, Depends, HTTPException, status
from google import genai
from google.genai import types

logger = logging.getLogger("ai_router")
router = APIRouter(prefix="/api/ai", tags=["Study Sessions AI"])

def _get_gemini_client() -> genai.Client:
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GEMINI_API_KEY is not configured on the backend. Please add it to .env.",
        )
    return genai.Client(api_key=api_key)


@router.post("/generate", response_model=GenerateSessionResponse, status_code=status.HTTP_200_OK)
async def generate_study_session(
    payload: GenerateSessionRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Sends uploaded lecture material (PDF, image, or notes text) to Gemini AI.
    Generates both a 30-minute exam summary and a 5-minute timed quiz in a single structured call.
    Results are persisted to the database and linked to the user account.
    """
    # 0. Quota Check (Free tier limit = 3 requests / day; Pro = unlimited)
    user_plan = current_user.get("plan", "free")
    requests_today = current_user.get("requests_today", 0)
    if user_plan == "free" and requests_today >= 3:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Daily free quota limit reached (3/3 requests). Upgrade to StudyBuddy Pro for unlimited study preps and unlimited quiz generation!",
        )

    client = _get_gemini_client()
    contents_list = []
    resolved_topic = payload.topic or "Lecture Material"
    file_path = None
    original_filename = None

    # 1. Resolve Input Material (File or Pasted Text)
    if payload.file_id:
        docs_col = get_documents_collection()
        user_id = str(current_user["_id"])
        doc = await docs_col.find_one({"file_id": payload.file_id, "user_id": user_id})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Uploaded document not found or you do not have permission to access it.",
            )

        original_filename = doc.get("original_filename", "Lecture Material")
        stored_filename = doc.get("stored_filename")
        file_path = os.path.join(settings.UPLOAD_DIR, stored_filename)
        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Stored file '{stored_filename}' was not found on server storage.",
            )

        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to read file from storage: {str(e)}",
            )

        mime_type = doc.get("mime_type", "application/pdf")
        file_part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
        contents_list.append(file_part)

        if not payload.topic:
            orig = doc.get("original_filename", "Lecture Material")
            resolved_topic = os.path.splitext(orig)[0].replace("_", " ").title()

    elif payload.notes_text and payload.notes_text.strip():
        contents_list.append(payload.notes_text.strip())
        if not payload.topic:
            resolved_topic = "Lecture Notes"
        original_filename = f"{resolved_topic}.txt"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide either a valid 'file_id' or 'notes_text' to generate study material.",
        )

    # 2. Expert System Prompt for Coordinated Summary & Quiz
    num_questions = max(1, min(20, payload.quiz_question_count or 5))
    prompt = (
        f"You are an elite university exam preparation tutor. "
        f"The subject/topic is: '{resolved_topic}'. "
        f"Analyze the attached course content thoroughly and generate an intensive 30-Minute Study Session guide:\n\n"
        f"1. 30-Minute High-Yield Study Summary:\n"
        f"   - An overview synthesizing the main themes.\n"
        f"   - Structured key concept breakdowns with bullet points covering critical takeaways.\n"
        f"   - Essential formulas, core definitions, and technical terms.\n"
        f"   - High-yield exam tips, common student mistakes, and mnemonics.\n\n"
        f"2. Timed Practice Quiz:\n"
        f"   - Generate exactly {num_questions} challenging, high-yield multiple choice questions testing conceptual comprehension.\n"
        f"   - Each question must provide exactly 4 distinct answer options.\n"
        f"   - Specify the 0-indexed position (0, 1, 2, or 3) of the correct answer.\n"
        f"   - Provide an educational explanation for why that option is correct.\n\n"
        f"Ensure strict conformity to the requested JSON schema."
    )
    contents_list.append(prompt)

    # 3. Request Structured Output via Gemini AI with Fallback
    candidate_models = [settings.GEMINI_MODEL]
    for alt in ["gemini-3.5-flash-lite", "gemini-3.5-flash"]:
        if alt not in candidate_models:
            candidate_models.append(alt)

    content = None
    last_error = None
    for model_name in candidate_models:
        try:
            logger.info(f"Generating study session with model '{model_name}'...")
            response = client.models.generate_content(
                model=model_name,
                contents=contents_list,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ExamPrepContent,
                    temperature=0.3,
                ),
            )
            parsed_data = json.loads(response.text)
            content = ExamPrepContent(**parsed_data)
            if content and content.quiz and len(content.quiz) > num_questions:
                content.quiz = content.quiz[:num_questions]
            logger.info(f"Successfully generated study session with '{model_name}'.")
            break
        except Exception as e:
            logger.warning(f"Generation with '{model_name}' encountered issue: {e}")
            last_error = e

    if not content:
        logger.error(f"All Gemini candidate models failed: {last_error}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini AI generation error: {str(last_error)}",
        )

    # 4. Save to Database
    history_id = str(uuid.uuid4())
    session_id = history_id
    now_iso = datetime.now(timezone.utc).isoformat()
    session_record = {
        "history_id": history_id,
        "session_id": session_id,
        "user_id": str(current_user["_id"]),
        "original_filename": original_filename or "Study Material",
        "file_id": payload.file_id,
        "topic": content.topic or resolved_topic,
        "mode": payload.mode,
        "summary": content.summary.model_dump(),
        "quiz": [q.model_dump() for q in content.quiz],
        "created_at": now_iso,
    }

    sessions_col = get_sessions_collection()
    await sessions_col.insert_one(session_record)

    # 5. Reward XP (+50 XP for session generation) and update level/badges
    users_col = get_users_collection()
    user_rec = await users_col.find_one({"_id": str(current_user["_id"])})
    new_xp = (user_rec.get("xp", 0) if user_rec else 0) + 50
    new_level = 1 + (new_xp // 200)
    badges_set = set(user_rec.get("badges", []) if user_rec else [])
    badges_set.add("first")
    if new_xp >= 400:
        badges_set.add("master")
    if new_xp >= 800:
        badges_set.add("prodigy")

    await users_col.update_one(
        {"_id": str(current_user["_id"])},
        {
            "$inc": {"xp": 50, "requests_today": 1},
            "$set": {
                "level": new_level,
                "badges": sorted(list(badges_set)),
            },
        },
    )

    # 6. Discard temporary uploaded file immediately (no persistent file storage)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            docs_col = get_documents_collection()
            await docs_col.delete_many({"file_id": payload.file_id})
            logger.info(f"Discarded temporary upload '{file_path}'.")
        except Exception as discard_err:
            logger.warning(f"Failed to discard temp file: {discard_err}")

    return GenerateSessionResponse(
        session_id=session_id,
        history_id=history_id,
        original_filename=original_filename or "Study Material",
        file_id=payload.file_id,
        topic=content.topic or resolved_topic,
        mode=payload.mode,
        summary=content.summary,
        quiz=content.quiz,
        created_at=now_iso,
        message="Study session generated successfully with Gemini AI!",
    )


@router.get("/session/{session_id}", response_model=GenerateSessionResponse)
async def get_study_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Retrieves a previously generated study pack."""
    sessions_col = get_sessions_collection()
    user_id = str(current_user["_id"])
    record = await sessions_col.find_one({
        "$or": [{"session_id": session_id}, {"history_id": session_id}],
        "user_id": user_id,
    })
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Study session not found or you do not have permission to view it.",
        )

    resolved_id = record.get("session_id") or record.get("history_id", "")
    return GenerateSessionResponse(
        session_id=resolved_id,
        history_id=record.get("history_id") or resolved_id,
        original_filename=record.get("original_filename") or f"{record.get('topic', 'Study Material')}.txt",
        file_id=record.get("file_id"),
        topic=record.get("topic", "Study Session"),
        mode=record.get("mode", "both"),
        summary=StudySummary(**record["summary"]),
        quiz=record.get("quiz", []),
        created_at=record.get("created_at", ""),
        message="Study session loaded successfully.",
    )


@router.post("/quiz/mega", response_model=MegaQuizResponse)
async def create_mega_quiz(
    payload: MegaQuizCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Combines quiz questions from multiple previously generated study sessions into a single Mega Quiz.
    Deduplicates questions and registers a new playable Mega Quiz session.
    """
    user_id = str(current_user["_id"])
    alt_user_id = str(current_user.get("user_id", ""))
    sessions_col = get_sessions_collection()

    matching_sessions = []
    for s_id in payload.session_ids:
        doc = await sessions_col.find_one({
            "user_id": user_id,
            "$or": [{"session_id": s_id}, {"history_id": s_id}]
        })
        if not doc and alt_user_id:
            doc = await sessions_col.find_one({
                "user_id": alt_user_id,
                "$or": [{"session_id": s_id}, {"history_id": s_id}]
            })
        if doc and doc not in matching_sessions:
            matching_sessions.append(doc)

    if not matching_sessions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="None of the specified study sessions were found for your account.",
        )

    # Aggregate & deduplicate quiz questions
    combined_quiz = []
    seen_questions = set()
    topics = []

    for s in matching_sessions:
        topic_name = s.get("topic")
        if topic_name and topic_name not in topics:
            topics.append(topic_name)

        raw_quiz = s.get("quiz", [])
        for q in raw_quiz:
            q_text = (q.get("question") if isinstance(q, dict) else getattr(q, "question", "")).strip()
            if q_text and q_text not in seen_questions:
                seen_questions.add(q_text)
                if isinstance(q, dict):
                    combined_quiz.append(QuizQuestion(**q))
                else:
                    combined_quiz.append(q)

    if not combined_quiz:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The selected study sessions do not contain any practice quiz questions.",
        )

    mega_session_id = f"mega_{uuid.uuid4().hex[:10]}"
    history_id = f"hist_{uuid.uuid4().hex[:10]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    topic_summary = " + ".join(topics[:3]) + ("..." if len(topics) > 3 else "")
    title = payload.title or f"Mega Quiz: {topic_summary}"

    mega_record = {
        "session_id": mega_session_id,
        "history_id": history_id,
        "user_id": user_id,
        "original_filename": f"Mega Quiz ({len(combined_quiz)} Questions)",
        "topic": title,
        "mode": "quiz",
        "is_mega_quiz": True,
        "source_session_ids": payload.session_ids,
        "summary": {
            "topic": title,
            "overview": f"Comprehensive mega practice quiz aggregated from {len(matching_sessions)} previous study sessions.",
            "key_concepts": [],
            "formulas_and_definitions": [],
            "high_yield_exam_tips": [],
        },
        "quiz": [q.model_dump() for q in combined_quiz],
        "created_at": now_iso,
    }

    await sessions_col.insert_one(mega_record)
    logger.info(f"Created Mega Quiz '{mega_session_id}' with {len(combined_quiz)} questions from {len(matching_sessions)} sessions.")

    return MegaQuizResponse(
        session_id=mega_session_id,
        history_id=history_id,
        topic=title,
        total_questions=len(combined_quiz),
        quiz=combined_quiz,
        source_session_ids=payload.session_ids,
        created_at=now_iso,
        message=f"Mega Quiz created with {len(combined_quiz)} questions across {len(matching_sessions)} study sessions!",
    )


@router.post("/quiz/submit", response_model=QuizResultResponse)
async def submit_quiz(
    payload: QuizSubmitRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Submits student quiz answers, calculates percentage score,
    awards XP, updates best score record, and returns detailed question review.
    """
    target_id = payload.session_id
    sessions_col = get_sessions_collection()
    user_id = str(current_user["_id"])
    alt_user_id = str(current_user.get("user_id", ""))
    record = await sessions_col.find_one({
        "session_id": target_id,
        "user_id": user_id,
    })
    if not record and alt_user_id:
        record = await sessions_col.find_one({
            "session_id": target_id,
            "user_id": alt_user_id,
        })
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz session not found.",
        )

    quiz_questions = record.get("quiz", [])
    total_questions = len(quiz_questions)
    if total_questions == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This session has no quiz questions.",
        )

    # Map user answers by question_index
    user_answers = {a.question_index: a.selected_option_index for a in payload.answers}

    correct_count = 0
    details = []

    for i, q in enumerate(quiz_questions):
        correct_idx = q.get("correct_answer_index", 0)
        selected_idx = user_answers.get(i, -1)
        is_correct = (selected_idx == correct_idx)
        if is_correct:
            correct_count += 1

        details.append(
            QuestionReviewDetail(
                question_index=i,
                question=q.get("question", ""),
                options=q.get("options", []),
                selected_option_index=selected_idx,
                correct_answer_index=correct_idx,
                is_correct=is_correct,
                explanation=q.get("explanation", ""),
            )
        )

    score_percent = round((correct_count / total_questions) * 100, 1)
    xp_earned = (correct_count * 10) + (20 if score_percent >= 80 else 0)

    # Update student profile stats, rank level, and badges
    users_col = get_users_collection()
    user = await users_col.find_one({"_id": user_id})
    old_best = float(user.get("best_quiz_score", 0.0)) if user else 0.0
    new_best = max(old_best, score_percent)
    current_xp = (user.get("xp", 0) if user else 0) + xp_earned
    new_level = 1 + (current_xp // 200)
    badges_set = set(user.get("badges", []) if user else [])

    if score_percent >= 80:
        badges_set.add("quiz")
    if score_percent == 100:
        badges_set.add("legend")
    if payload.time_taken_seconds > 0 and payload.time_taken_seconds <= 120 and score_percent >= 60:
        badges_set.add("speed")
    if current_xp >= 400:
        badges_set.add("master")
    if current_xp >= 800:
        badges_set.add("prodigy")

    await users_col.update_one(
        {"_id": user_id},
        {
            "$inc": {"xp": xp_earned},
            "$set": {
                "best_quiz_score": new_best,
                "level": new_level,
                "badges": sorted(list(badges_set)),
            },
        },
    )

    # Record latest quiz score on session to feed subject skill radar
    await sessions_col.update_one(
        {"session_id": target_id},
        {"$set": {"last_score_percent": score_percent}}
    )

    return QuizResultResponse(
        session_id=target_id or "",
        score_percent=score_percent,
        correct_count=correct_count,
        total_questions=total_questions,
        xp_earned=xp_earned,
        details=details,
        message=f"Quiz completed! You scored {correct_count}/{total_questions} ({score_percent}%). +{xp_earned} XP awarded!",
    )

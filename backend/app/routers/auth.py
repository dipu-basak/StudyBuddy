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
    from app.database import get_users_collection, get_sessions_collection
    from app.schemas import AuthResponse, LoginRequest, SignupRequest, UserResponse
    from app.security import create_access_token, decode_access_token, hash_password, verify_password
except ImportError:
    from database import get_users_collection, get_sessions_collection
    from schemas import AuthResponse, LoginRequest, SignupRequest, UserResponse
    from security import create_access_token, decode_access_token, hash_password, verify_password

from fastapi import APIRouter, Depends, Header, HTTPException, status

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Dependency: Validate Bearer JWT token and return authenticated user document."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication token. Please log in.",
        )

    token = authorization.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expired or invalid token. Please log in again.",
        )

    user_id = payload.get("sub")
    collection = get_users_collection()
    
    try:
        from bson import ObjectId
        obj_id = ObjectId(user_id) if ObjectId.is_valid(user_id) else None
    except Exception:
        obj_id = None

    query = {"$or": [{"_id": user_id}, {"_id": obj_id}]} if obj_id else {"_id": user_id}
    user = await collection.find_one(query)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found.",
        )
    return user


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest):
    """Register a new student account with clean zero statistics."""
    collection = get_users_collection()
    normalized_email = payload.email.lower().strip()

    # Check for existing email
    existing_user = await collection.find_one({"email": normalized_email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists. Please log in.",
        )

    # Hash password with bcrypt
    password_hash = hash_password(payload.password)
    now = datetime.now(timezone.utc).isoformat()

    user_id = str(uuid.uuid4())
    user_doc = {
        "_id": user_id,
        "name": payload.name.strip(),
        "email": normalized_email,
        "password_hash": password_hash,
        "plan": "free",
        "streak": 0,
        "xp": 0,
        "level": 1,
        "total_uploads": 0,
        "best_quiz_score": 0.0,
        "badges": [],
        "requests_today": 0,
        "avatar": None,
        "created_at": now,
        "updated_at": now,
    }

    await collection.insert_one(user_doc)

    # Issue JWT token
    access_token = create_access_token(data={"sub": user_id, "email": normalized_email})

    return AuthResponse(
        access_token=access_token,
        token_type="bearer",
        message="Registration successful! Welcome to StudyBuddy.",
        user=UserResponse(
            id=user_id,
            name=user_doc["name"],
            email=user_doc["email"],
            plan=user_doc["plan"],
            streak=user_doc["streak"],
            xp=user_doc["xp"],
            level=user_doc["level"],
            total_uploads=user_doc["total_uploads"],
            best_quiz_score=user_doc["best_quiz_score"],
            badges=user_doc["badges"],
            requests_today=user_doc["requests_today"],
            avatar=user_doc["avatar"],
            created_at=user_doc["created_at"],
        ),
    )


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest):
    """Authenticate with email and password."""
    collection = get_users_collection()
    normalized_email = payload.email.lower().strip()

    user = await collection.find_one({"email": normalized_email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password. Please try again.",
        )

    # Verify password hash
    if not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password. Please try again.",
        )

    user_id = str(user.get("_id"))
    access_token = create_access_token(data={"sub": user_id, "email": normalized_email})

    return AuthResponse(
        access_token=access_token,
        token_type="bearer",
        message="Login successful! Redirecting to your workspace.",
        user=UserResponse(
            id=user_id,
            name=user.get("name", "Student"),
            email=user.get("email"),
            plan=user.get("plan", "free"),
            streak=user.get("streak", 0),
            xp=user.get("xp", 0),
            level=user.get("level", 1),
            total_uploads=user.get("total_uploads", 0),
            best_quiz_score=float(user.get("best_quiz_score", 0.0)),
            badges=user.get("badges", []),
            requests_today=user.get("requests_today", 0),
            avatar=user.get("avatar"),
            created_at=str(user.get("created_at")),
        ),
    )


async def _calculate_user_subject_skills(user_id: str, alt_user_id: str = "") -> dict:
    """
    Computes subject mastery percentages strictly based on student's actual session history.
    Never invents or pads unstudied subjects (e.g. Chemistry, Physics) that do not exist in history.
    """
    try:
        sessions_col = get_sessions_collection()
        res = sessions_col.find({"user_id": user_id})
        if hasattr(res, "to_list"):
            sessions = await res.to_list(length=200)
        else:
            sessions = await res

        if not sessions and alt_user_id:
            res_alt = sessions_col.find({"user_id": alt_user_id})
            if hasattr(res_alt, "to_list"):
                sessions = await res_alt.to_list(length=200)
            else:
                sessions = await res_alt

        if not sessions:
            return {}

        disciplines = {
            "Computer Architecture & Hardware": [
                "microprocessor", "intel", "8080", "cpu", "accumulator", "register", "hardware", "assembly", "chip", "architecture", "embedded", "instruction set", "datapath"
            ],
            "Algorithms & Data Structures": [
                "algorithm", "sorting", "data structure", "graph", "tree", "complexity", "big-o", "search", "recursion", "mit6 006", "006", "hash", "dynamic programming"
            ],
            "Digital Logic & Circuits": [
                "logisim", "logic gate", "circuit", "boolean", "flip flop", "multiplexer", "karnaugh", "truth table", "combinational", "sequential"
            ],
            "Software Engineering & Web": [
                "software", "testing", "web", "frontend", "backend", "api", "database", "sql", "python", "git", "fullstack", "react", "fastapi"
            ],
            "Biology & Life Sciences": [
                "bio", "cell", "plant", "উদ্ভিদ", "বংশ বৃদ্ধি", "gene", "dna", "genetics", "organism", "ecology", "photosynthesis", "respiration", "botany", "zoology"
            ],
            "Social Sciences & Humanities": [
                "somaj", "সমাজ", "সামাজিকীকরণ", "social", "history", "sociology", "philosophy", "civics", "culture", "humanities", "literature", "language"
            ],
            "Mathematics & Statistics": [
                "math", "calculus", "algebra", "linear", "matrix", "statistics", "probability", "derivative", "integral", "geometry", "trigonometry"
            ],
            "Physics & Physical Sciences": [
                "physic", "mechanic", "thermodynamic", "electromagnetism", "quantum", "optics", "force", "gravity", "wave", "kinematics", "newton"
            ],
            "Chemistry & Molecular Sciences": [
                "chem", "reaction", "organic", "periodic", "acid", "base", "stoichiometry", "bond", "equilibrium", "inorganic", "polymer"
            ],
            "Business & Economics": [
                "business", "economic", "finance", "accounting", "marketing", "management", "macroeconomic", "microeconomic"
            ],
        }

        subject_scores = {}
        for s in sessions:
            text = f"{s.get('topic') or ''} {s.get('original_filename') or ''}".lower()
            matched = False
            for disc, kws in disciplines.items():
                if any(kw in text for kw in kws):
                    score = s.get("last_score_percent")
                    if score is None:
                        score = 75.0 if s.get("quiz") else 65.0
                    subject_scores.setdefault(disc, []).append(float(score))
                    matched = True
                    break
            if not matched:
                score = s.get("last_score_percent") or 65.0
                subject_scores.setdefault("General Academic Studies", []).append(float(score))

        final_skills = {}
        for disc, scores in subject_scores.items():
            avg_score = sum(scores) / len(scores)
            volume_bonus = min(20.0, len(scores) * 4.0)
            final_skills[disc] = round(min(100.0, max(25.0, avg_score + volume_bonus)), 1)

        return final_skills
    except Exception:
        return {}


@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    """Fetch profile of currently logged-in student and ensure dynamic achievements are synced."""
    user_id = str(current_user.get("_id"))
    alt_user_id = str(current_user.get("user_id", ""))
    xp_val = current_user.get("xp", 0)
    level_val = 1 + (xp_val // 200)
    best_score = float(current_user.get("best_quiz_score", 0.0))
    total_uploads = current_user.get("total_uploads", 0)
    streak_val = current_user.get("streak", 0)

    # Calculate dynamic subject mastery radar skills
    skills_map = await _calculate_user_subject_skills(user_id, alt_user_id)

    # Dynamically verify and award qualifying badges
    badges_set = set(current_user.get("badges", []))
    if xp_val >= 50:
        badges_set.add("first")
    if best_score >= 80:
        badges_set.add("quiz")
    if best_score >= 100:
        badges_set.add("legend")
    if total_uploads >= 3:
        badges_set.add("scholar")
    if streak_val >= 3:
        badges_set.add("week")
    if xp_val >= 400:
        badges_set.add("master")
    if xp_val >= 800:
        badges_set.add("prodigy")

    badges_list = sorted(list(badges_set))
    if badges_list != current_user.get("badges", []) or level_val != current_user.get("level", 1):
        users_col = get_users_collection()
        await users_col.update_one(
            {"_id": str(current_user.get("_id"))},
            {"$set": {"badges": badges_list, "level": level_val}},
        )

    return UserResponse(
        id=str(current_user.get("_id")),
        name=current_user.get("name", "Student"),
        email=current_user.get("email"),
        plan=current_user.get("plan", "free"),
        streak=streak_val,
        xp=xp_val,
        level=level_val,
        total_uploads=total_uploads,
        best_quiz_score=best_score,
        badges=badges_list,
        requests_today=current_user.get("requests_today", 0),
        avatar=current_user.get("avatar"),
        created_at=str(current_user.get("created_at")),
        subject_skills=skills_map,
    )

<p align="center">
  <img width="170" height="170" alt="Untitled design (2)" src="https://github.com/user-attachments/assets/bcab3864-c82b-4448-9090-b7c0a5ed20e9" />
</p>


<div align="center">

# StudyBuddy - Exam Prep AI

**Turn dense lecture slides, PDFs, and raw notes into structured 30-minute study guides and timed practice quizzes.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Flet](https://img.shields.io/badge/Flet-1.0%2B-02569B?style=for-the-badge&logo=flutter&logoColor=white)](https://flet.dev/)
[![MongoDB](https://img.shields.io/badge/MongoDB-Motor%20%2B%20JSON%20Fallback-47A248?style=for-the-badge&logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![Gemini AI](https://img.shields.io/badge/Google%20Gemini-GenAI%20SDK-8E75B2?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![SSLCommerz](https://img.shields.io/badge/SSLCommerz-Sandbox%20Ready-F59E0B?style=for-the-badge)](https://developer.sslcommerz.com/)

[Features](#-key-features) • [Architecture](#%EF%B8%8F-architecture) • [Quick Start](#-quick-start) • [API Reference](#-api-reference) • [Payment Sandbox](#-sslcommerz-sandbox--monitoring)

</div>

---

## 📘 About Us

StudyBuddy is an AI-powered exam preparation platform built to help students turn dense lecture slides, PDFs, and raw class notes into clear, focused study material in seconds.

---

## 🚩 Our Mission

Exam preparation shouldn't mean spending hours drowning in unorganized pages. Our goal is to make studying faster, smarter, and more engaging by pairing concise 30-minute AI study guides with active-recall timed practice quizzes.

---

## 👥 Development Team

<div align="center">
<table>
  <tr>
    <td align="center" width="33.33%">
      <a href="https://github.com/Shadow-ranger01">
        <img src="https://github.com/Shadow-ranger01.png?size=120" width="100" style="border-radius: 50%;" alt="Shadow-ranger01" />
        <br />
        <sub><b>Rafi </b></sub>
      </a>
      <br />
      <a href="https://github.com/Shadow-ranger01">
        <img src="https://img.shields.io/badge/GitHub-Profile-181717?style=flat&logo=github" alt="GitHub" />
      </a>
    </td>
    <td align="center" width="33.33%">
      <a href="https://github.com/Oyshikee-Chakrabarty">
        <img src="https://github.com/Oyshikee-Chakrabarty.png?size=120" width="100" style="border-radius: 50%;" alt="Oyshikee Chakrabarty" />
        <br />
        <sub><b>Oyshikee </b></sub>
      </a>
      <br />
      <a href="https://github.com/Oyshikee-Chakrabarty">
        <img src="https://img.shields.io/badge/GitHub-Profile-181717?style=flat&logo=github" alt="GitHub" />
      </a>
    </td>
    <td align="center" width="33.33%">
      <a href="https://github.com/dipu-basak">
        <img src="https://github.com/dipu-basak.png?size=120" width="100" style="border-radius: 50%;" alt="Dipu Basak" />
        <br />
        <sub><b>Dipu </b></sub>
      </a>
      <br />
      <a href="https://github.com/dipu-basak">
        <img src="https://img.shields.io/badge/GitHub-Profile-181717?style=flat&logo=github" alt="GitHub" />
      </a>
    </td>
  </tr>
</table>
</div>

---

## 📖 Overview

**StudyBuddy** is a full-stack AI-powered exam preparation platform built with a **FastAPI** backend and a **Flet** Soft UI frontend. Students can upload lecture PDFs, slide images, or pasted notes to generate structured study summaries and interactive timed quizzes powered by the **Google Gemini API**.

The platform includes persistent user study history, a multi-session **Mega Quiz Builder**, gamified XP/level progression with achievements, a dynamic **Subject Mastery Spider Chart** calibrated from real study history, and an integrated **SSLCommerz Developer Sandbox** for Pro upgrades.

---

## ✨ Key Features

- **🧠 Multimodal AI Study Engine (`Gemini GenAI SDK`)**
  - Accepts `.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.txt` uploads or pasted lecture text.
  - Generates structured **30-Minute Study Summaries** (Executive Overview, Key Concepts, Formulas & Definitions, High-Yield Exam Tips) and **Timed Practice Quizzes** with selectable lengths (`3`, `5`, `10`, or `15` questions).
  - Supports flexible generation modes: `summary`, `quiz`, or `both`.

- **🛡️ Hardened File Upload Security**
  - Strict extension allowlisting and executable blacklist (`file_security.py`).
  - Magic-byte signature inspection to reject disguised binaries/archives, filename sanitization against path traversal, SHA-256 hashing, and a 20 MB file size cap.

- **📚 Persistent Study History & Mega Quiz Builder**
  - Automatically saves generated study materials per authenticated user, ordered newest-first.
  - Review past notes, retake quizzes, or delete individual sessions (`GET/DELETE /api/history`).
  - **⚡ Mega Quiz Builder:** Select multiple past sessions in History to pool and deduplicate questions into a single unified mock exam (`POST /api/ai/quiz/mega`).

- **🏆 Gamification, Achievements & Scholar Profile**
  - Real-time **XP**, **Levels** (`1 + xp // 200`), daily **Streaks**, **Best Quiz Score**, and dynamic **Badges** (*First Study*, *Quiz Master*, *Scholar*, *Streak*, *Prodigy*, *Legend*).
  - **Dynamic Subject Mastery Radar:** Native vector spider/radar chart rendered via `flet.canvas.Canvas`, dynamically calibrated **strictly from the actual academic disciplines present in the user's study history** (zero hardcoded phantom subjects).

- **💳 SSLCommerz Developer Sandbox & XP Discount**
  - **Free Tier:** 3 AI generations/day.
  - **StudyBuddy Pro:** Unlimited daily generations and quiz generation (`৳499.00 BDT`).
  - **Scholar XP Discount:** Students with `> 250 XP` automatically unlock a **5% discount** (`৳474.05 BDT`).
  - Includes live SSLCommerz sandbox session creation, automatic local interactive sandbox checkout fallback (`/api/payment/sandbox-checkout/{tran_id}`), IPN webhook support, status polling, and a CLI payment monitor.

- **🗄️ Zero-Config Database Resilience**
  - Connects asynchronously to **MongoDB** via `motor` with automatic fallback to `LocalJsonMongoCollection` (`*_local_db.json`) so the app runs cleanly even without a MongoDB server.

---

## 🏗️ Architecture

```text
internet_programming/
├── 2nd_phase/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── routers/
│   │   │   │   ├── auth.py          # Signup, login, JWT auth, profile & dynamic subject skills
│   │   │   │   ├── upload.py        # Secure file upload & document metadata endpoints
│   │   │   │   ├── ai.py            # Gemini AI generation, Mega Quiz & quiz grading
│   │   │   │   ├── history.py       # Persistent per-user study history CRUD
│   │   │   │   └── payment.py       # SSLCommerz sandbox checkout, IPN, status & transactions
│   │   │   ├── config.py            # Environment-backed Settings dataclass
│   │   │   ├── database.py          # Async Motor MongoDB + LocalJsonMongoCollection fallback
│   │   │   ├── file_security.py     # Filename sanitization, magic-byte & extension validation
│   │   │   ├── main.py              # FastAPI entrypoint & router registration
│   │   │   ├── schemas.py           # Centralized Pydantic v2 request/response models
│   │   │   └── security.py          # Bcrypt password hashing & HS256 PyJWT utilities
│   │   └── .env                     # Environment configuration (not committed)
│   ├── frontend/
│   │   ├── api_client.py            # Async httpx client for all backend API endpoints
│   │   ├── auth_view.py             # Flet Sign Up / Log In UI
│   │   ├── dashboard_view.py        # Soft UI Dashboard, History, Achievements, Profile & Radar Chart
│   │   ├── main.py                  # Flet app entry point
│   │   ├── theme.py                 # Soft UI palette, shadows, and card builders
│   │   └── requirements.txt         # Frontend packages (flet, httpx)
│   ├── monitor_payments.py          # CLI dashboard to audit sandbox payment transactions
│   ├── requirements.txt             # Combined project dependencies
│   └── README.md                    # Phase-local quick reference
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- A **Google Gemini API Key** ([Google AI Studio](https://aistudio.google.com/))
- *(Optional)* A **MongoDB** URI (local or Atlas). If omitted or unreachable, StudyBuddy automatically falls back to local JSON storage.

### 1. Clone & Install Dependencies

```bash
git clone <your-repository-url>
cd internet_programming
python -m venv 2nd_phase/venv
```

Activate the virtual environment and install dependencies:

**Windows (PowerShell):**
```powershell
.\2nd_phase\venv\Scripts\Activate.ps1
pip install -r 2nd_phase/requirements.txt
```

**macOS / Linux:**
```bash
source 2nd_phase/venv/bin/activate
pip install -r 2nd_phase/requirements.txt
```

### 2. Configure Environment Variables

Create `2nd_phase/backend/.env` (see [Environment Variables](#%EF%B8%8F-environment-variables)):

```env
GEMINI_API_KEY=your_gemini_api_key_here
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=exam_prep_ai
```

### 3. Run the Application

Open two terminals from the repository root:

**Terminal 1 — FastAPI Backend:**
```bash
cd 2nd_phase/backend
uvicorn app.main:app --port 8000 --reload
```
- API Root: `http://127.0.0.1:8000`
- Interactive Swagger Docs: `http://127.0.0.1:8000/docs`

**Terminal 2 — Flet Frontend:**
```bash
cd 2nd_phase/frontend
python main.py
```

---

## 📡 API Reference

### Authentication (`/api/auth`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/auth/signup` | Register a new student account and return a JWT token. |
| `POST` | `/api/auth/login` | Authenticate user credentials and return a JWT token. |
| `GET` | `/api/auth/me` | Fetch profile, synced badges, XP/level, and dynamic `subject_skills`. |

### File Uploads (`/api/upload`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/upload` | Validate (magic-byte + extension + size) and store a lecture file. |
| `GET` | `/api/upload/documents` | List documents uploaded by the authenticated user. |
| `GET` | `/api/upload/documents/{file_id}` | Retrieve metadata for a specific uploaded document. |

### AI Study Engine & Quizzes (`/api/ai`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/ai/generate` | Generate structured study summary and/or timed quiz via Gemini AI. |
| `GET` | `/api/ai/session/{session_id}` | Fetch a specific generated study session. |
| `POST` | `/api/ai/quiz/mega` | Combine & deduplicate quiz questions from multiple past sessions. |
| `POST` | `/api/ai/quiz/submit` | Grade quiz answers, award XP, update streak/best score, and calibrate skills. |

### Study History (`/api/history`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/history` | List all saved study sessions for the logged-in user (newest first). |
| `GET` | `/api/history/{history_id}` | Retrieve a single study history record (owner-verified). |
| `DELETE` | `/api/history/{history_id}` | Delete a specific history record (owner-verified). |

### Payment & SSLCommerz Sandbox (`/api/payment`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/payment/quote` | Get Pro pricing quote including automatic 5% discount when `XP > 250`. |
| `POST` | `/api/payment/initiate` | Create a pending transaction and return the SSLCommerz/sandbox checkout URL. |
| `GET` | `/api/payment/sandbox-checkout/{transaction_id}` | Built-in interactive sandbox checkout page (bKash, Nagad, Cards). |
| `GET/POST` | `/api/payment/success`, `/fail`, `/cancel` | Gateway callback handlers that update transaction state and upgrade plan. |
| `POST` | `/api/payment/ipn` | Asynchronous Instant Payment Notification (IPN) webhook listener. |
| `GET` | `/api/payment/status/{transaction_id}` | Poll transaction status from the Flet frontend. |
| `GET` | `/api/payment/transactions` | List the authenticated user's payment transaction ledger. |
| `POST` | `/api/payment/simulate-success/{transaction_id}` | Developer sandbox helper for instant one-click demo completion. |

### Health Check
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Returns backend service health, name, and version. |

---

## 💳 SSLCommerz Sandbox & Monitoring

To inspect sandbox transactions, revenue metrics, and active Pro upgrades in real time from the terminal:

```bash
python 2nd_phase/monitor_payments.py
```

You can also test and monitor every payment endpoint interactively via Swagger UI at:
`http://127.0.0.1:8000/docs#/Payment%20%26%20SSLCommerz%20Sandbox`

---

## 🛠️ Tech Stack

- **Frontend:** [Flet](https://flet.dev/) (`1.0+`), Native Vector `flet.canvas.Canvas`, `httpx`
- **Backend:** [FastAPI](https://fastapi.tiangolo.com/), Uvicorn, Pydantic v2
- **AI:** [Google GenAI SDK](https://pypi.org/project/google-genai/) (`google-genai`)
- **Database:** MongoDB (`motor` / `pymongo`) + `LocalJsonMongoCollection` JSON fallback
- **Security:** `bcrypt`, `PyJWT` (`HS256`), custom magic-byte & extension validation
- **Payments:** SSLCommerz v4 Sandbox API + built-in offline simulation gateway

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

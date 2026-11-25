import httpx
from typing import Optional, Tuple, List

class ApiClient:
    def __init__(self, host: str = "http://127.0.0.1:8000"):
        self.host = host.rstrip("/")
        self.auth_base = f"{self.host}/api/auth"
        self.upload_base = f"{self.host}/api/upload"

    # ── Authentication ──────────────────────────────────────────────
    async def signup(self, name: str, email: str, password: str) -> Tuple[bool, str, Optional[dict], Optional[str]]:
        """
        Registers a new user.
        Returns: (success, message, user_data, access_token)
        """
        url = f"{self.auth_base}/signup"
        payload = {
            "name": name.strip(),
            "email": email.strip(),
            "password": password,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                data = response.json()
                if response.status_code == 201:
                    return True, data.get("message", "Signup successful!"), data.get("user"), data.get("access_token")
                else:
                    detail = data.get("detail", "Registration failed.")
                    if isinstance(detail, list):
                        detail = detail[0].get("msg", "Invalid input.")
                    return False, str(detail), None, None
        except httpx.ConnectError:
            return False, "Cannot connect to FastAPI backend at http://127.0.0.1:8000. Please start the backend.", None, None
        except httpx.TimeoutException:
            return False, "Request to backend timed out. Please try again.", None, None
        except Exception as e:
            err_msg = str(e).strip() or "Connection error"
            return False, f"Network error: {err_msg}", None, None

    async def login(self, email: str, password: str) -> Tuple[bool, str, Optional[dict], Optional[str]]:
        """
        Authenticates an existing user.
        Returns: (success, message, user_data, access_token)
        """
        url = f"{self.auth_base}/login"
        payload = {
            "email": email.strip(),
            "password": password,
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(url, json=payload)
                data = response.json()
                if response.status_code == 200:
                    return True, data.get("message", "Login successful!"), data.get("user"), data.get("access_token")
                else:
                    detail = data.get("detail", "Invalid email or password.")
                    if isinstance(detail, list):
                        detail = detail[0].get("msg", "Invalid credentials format.")
                    return False, str(detail), None, None
        except httpx.ConnectError:
            return False, "Cannot connect to FastAPI backend at http://127.0.0.1:8000. Please start the backend.", None, None
        except httpx.TimeoutException:
            return False, "Request to backend timed out. Please try again.", None, None
        except Exception as e:
            err_msg = str(e).strip() or "Connection error"
            return False, f"Network error: {err_msg}", None, None

    async def get_me(self, token: str) -> Tuple[bool, str, Optional[dict]]:
        """
        Fetches the current user's profile using their JWT access token.
        """
        url = f"{self.auth_base}/me"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return True, "Profile loaded", response.json()
                return False, "Session expired or invalid token.", None
        except Exception as e:
            return False, str(e), None

    # ── File Upload & Document Management ───────────────────────────
    async def upload_file(
        self,
        filename: str,
        file_bytes: bytes,
        token: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Uploads and validates a lecture file through the backend /api/upload endpoint.
        Returns: (success, message, file_metadata)
        """
        url = f"{self.upload_base}/"
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            files = {"file": (filename, file_bytes)}
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, files=files, headers=headers)
                data = response.json()
                if response.status_code == 201:
                    return True, data.get("message", "File uploaded successfully!"), data
                else:
                    detail = data.get("detail", "File upload failed.")
                    if isinstance(detail, list):
                        detail = detail[0].get("msg", "File validation error.")
                    return False, str(detail), None
        except httpx.ConnectError:
            return False, "Cannot connect to FastAPI backend at http://127.0.0.1:8000. Please start the backend.", None
        except Exception as e:
            return False, f"Upload error: {str(e)}", None

    async def list_documents(self, token: str) -> Tuple[bool, str, List[dict]]:
        """
        Fetches the list of uploaded lecture documents for the current user.
        """
        url = f"{self.upload_base}/documents"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    return True, "Documents loaded", data.get("documents", [])
                return False, "Failed to load documents", []
        except Exception as e:
            return False, str(e), []

    # ── AI Study Sessions ───────────────────────────────────────────
    async def generate_study_session(
        self,
        file_id: Optional[str] = None,
        notes_text: Optional[str] = None,
        topic: Optional[str] = None,
        mode: str = "both",
        quiz_question_count: int = 5,
        token: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Calls /api/ai/generate to analyze material with Gemini AI and produce
        both a 30-minute exam summary and a timed quiz with the selected number of questions.
        """
        url = f"{self.host}/api/ai/generate"
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        payload = {
            "file_id": file_id,
            "notes_text": notes_text,
            "topic": topic,
            "mode": mode,
            "quiz_question_count": quiz_question_count,
        }
        try:
            # AI generation takes 3-15 seconds depending on document length
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                data = response.json()
                if response.status_code == 200:
                    return True, data.get("message", "Study session generated!"), data
                else:
                    detail = data.get("detail", "Failed to generate study session.")
                    if isinstance(detail, list):
                        detail = detail[0].get("msg", "Validation error.")
                    return False, str(detail), None
        except httpx.ConnectError:
            return False, "Cannot connect to backend at http://127.0.0.1:8000.", None
        except httpx.ReadTimeout:
            return False, "AI generation timed out. The server is still processing.", None
        except Exception as e:
            return False, f"AI generation error: {str(e)}", None

    async def create_mega_quiz(
        self,
        session_ids: List[str],
        title: Optional[str] = None,
        token: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Calls /api/ai/quiz/mega to aggregate multiple past study sessions into a single Mega Quiz.
        """
        url = f"{self.host}/api/ai/quiz/mega"
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        payload = {"session_ids": session_ids, "title": title}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                data = resp.json()
                if resp.status_code == 200:
                    return True, data.get("message", "Mega Quiz created!"), data
                detail = data.get("detail", "Failed to create Mega Quiz.")
                return False, str(detail), None
        except Exception as e:
            return False, f"Mega Quiz error: {str(e)}", None

    async def get_study_session(self, session_id: str, token: Optional[str] = None) -> Tuple[bool, str, Optional[dict]]:
        """Retrieves an existing study session by ID."""
        url = f"{self.host}/api/ai/session/{session_id}"
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return True, "Loaded", response.json()
                return False, response.json().get("detail", "Not found"), None
        except Exception as e:
            return False, str(e), None

    async def submit_quiz(
        self,
        session_id: str,
        answers: List[dict],
        time_taken_seconds: int = 0,
        token: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[dict]]:
        """Submits student quiz answers for scoring and XP reward."""
        url = f"{self.host}/api/ai/quiz/submit"
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        payload = {
            "session_id": session_id,
            "answers": answers,
            "time_taken_seconds": time_taken_seconds,
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                data = response.json()
                if response.status_code == 200:
                    return True, data.get("message", "Quiz scored!"), data
                return False, data.get("detail", "Quiz submission failed"), None
        except Exception as e:
            return False, str(e), None

    # ── Study History ───────────────────────────────────────────────
    async def get_history(self, token: str) -> Tuple[bool, str, List[dict]]:
        """
        Retrieves all previous study sessions for the authenticated user, newest first.
        Returns: (success, message, history_items)
        """
        url = f"{self.host}/api/history"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    return True, data.get("message", "History loaded"), data.get("history", [])
                detail = response.json().get("detail", "Failed to fetch history")
                return False, str(detail), []
        except httpx.ConnectError:
            return False, "Cannot connect to FastAPI backend at http://127.0.0.1:8000.", []
        except Exception as e:
            return False, f"History error: {str(e)}", []

    async def get_history_item(self, history_id: str, token: str) -> Tuple[bool, str, Optional[dict]]:
        """Retrieves a single study history record by ID."""
        url = f"{self.host}/api/history/{history_id}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return True, "Loaded", response.json()
                detail = response.json().get("detail", "History item not found")
                return False, str(detail), None
        except Exception as e:
            return False, str(e), None

    async def delete_history_item(self, history_id: str, token: str) -> Tuple[bool, str]:
        """
        Deletes a specific history record for the authenticated user.
        Returns: (success, message)
        """
        url = f"{self.host}/api/history/{history_id}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.delete(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    return True, data.get("message", "History record deleted successfully.")
                detail = response.json().get("detail", "Failed to delete history record.")
                return False, str(detail)
        except Exception as e:
            return False, f"Delete error: {str(e)}"

    # ── SSLCommerz Sandbox Payment Gateway ──────────────────────────
    async def get_payment_quote(self, token: str) -> Tuple[bool, str, Optional[dict]]:
        """Fetches pricing quote for StudyBuddy Pro including dynamic 5% Scholar discount if XP > 250."""
        url = f"{self.host}/api/payment/quote"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return True, "Quote loaded", resp.json()
                return False, resp.json().get("detail", "Failed to fetch pricing quote"), None
        except Exception as e:
            return False, str(e), None

    async def initiate_payment(self, token: str, cus_phone: str = "01711111111") -> Tuple[bool, str, Optional[dict]]:
        """Initializes SSLCommerz Sandbox payment session and returns Gateway URL."""
        url = f"{self.host}/api/payment/initiate"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json={"cus_phone": cus_phone}, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return True, data.get("message", "Payment session created"), data
                return False, resp.json().get("detail", "Failed to initiate payment"), None
        except Exception as e:
            return False, str(e), None

    async def get_payment_status(self, token: str, transaction_id: str) -> Tuple[bool, str, Optional[dict]]:
        """Checks the status of an active transaction and whether the user is now Pro."""
        url = f"{self.host}/api/payment/status/{transaction_id}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return True, "Status retrieved", resp.json()
                return False, resp.json().get("detail", "Failed to get payment status"), None
        except Exception as e:
            return False, str(e), None

    async def simulate_payment_success(self, token: str, transaction_id: str) -> Tuple[bool, str, Optional[dict]]:
        """Simulates instant sandbox payment completion for quick in-app demos."""
        url = f"{self.host}/api/payment/simulate-success/{transaction_id}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers)
                if resp.status_code == 200:
                    return True, "Payment simulated successfully", resp.json()
                return False, resp.json().get("detail", "Failed to simulate payment"), None
        except Exception as e:
            return False, str(e), None

# Backwards compatibility aliases
AuthApiClient = ApiClient
api_client = ApiClient()

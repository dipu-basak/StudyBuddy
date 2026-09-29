import httpx
from typing import Optional, Tuple

class AuthApiClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000/api/auth"):
        self.base_url = base_url.rstrip("/")

    async def signup(self, name: str, email: str, password: str) -> Tuple[bool, str, Optional[dict], Optional[str]]:
        """
        Registers a new user.
        Returns: (success, message, user_data, access_token)
        """
        url = f"{self.base_url}/signup"
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
        except Exception as e:
            return False, f"Network error: {str(e)}", None, None

    async def login(self, email: str, password: str) -> Tuple[bool, str, Optional[dict], Optional[str]]:
        """
        Authenticates an existing user.
        Returns: (success, message, user_data, access_token)
        """
        url = f"{self.base_url}/login"
        payload = {
            "email": email.strip(),
            "password": password,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
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
        except Exception as e:
            return False, f"Network error: {str(e)}", None, None

    async def get_me(self, token: str) -> Tuple[bool, str, Optional[dict]]:
        """
        Fetches the current user's profile using their JWT access token.
        """
        url = f"{self.base_url}/me"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return True, "Profile loaded", response.json()
                return False, "Session expired or invalid token.", None
        except Exception as e:
            return False, str(e), None

api_client = AuthApiClient()

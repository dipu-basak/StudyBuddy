import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from typing import Any, Optional

# Path resolution
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
for _path in [_parent_dir, _current_dir]:
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from app.config import settings
except ImportError:
    from config import settings

logger = logging.getLogger("database")

class LocalJsonMongoCollection:
    """
    Asynchronous Mongo-compatible collection fallback.
    Used when local MongoDB daemon is not running ('no need to install mongo').
    Persists data to JSON files in 1st_phase/backend/.
    """
    def __init__(self, db_file: str = "users_local_db.json"):
        self.db_path = os.path.join(_parent_dir, db_file)
        self._lock = asyncio.Lock()
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.db_path):
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump([], f)

    def _read_data(self) -> list[dict]:
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _write_data(self, data: list[dict]):
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    async def find_one(self, query: dict) -> Optional[dict]:
        async with self._lock:
            data = self._read_data()
            for doc in data:
                match = True
                for k, v in query.items():
                    if k == "_id":
                        if str(doc.get("_id")) != str(v):
                            match = False
                            break
                    elif doc.get(k) != v:
                        match = False
                        break
                if match:
                    return doc.copy()
            return None

    async def find(self, query: dict) -> list[dict]:
        """Find all matching documents."""
        async with self._lock:
            data = self._read_data()
            results = []
            for doc in data:
                match = True
                for k, v in query.items():
                    if k == "_id":
                        if str(doc.get("_id")) != str(v):
                            match = False
                            break
                    elif doc.get(k) != v:
                        match = False
                        break
                if match:
                    results.append(doc.copy())
            return results

    async def insert_one(self, doc: dict) -> Any:
        async with self._lock:
            data = self._read_data()
            new_doc = doc.copy()
            if "_id" not in new_doc:
                new_doc["_id"] = str(uuid.uuid4())
            else:
                new_doc["_id"] = str(new_doc["_id"])
            data.append(new_doc)
            self._write_data(data)
            
            class InsertResult:
                def __init__(self, inserted_id):
                    self.inserted_id = inserted_id
            return InsertResult(new_doc["_id"])

    async def count_documents(self, query: dict) -> int:
        async with self._lock:
            data = self._read_data()
            count = 0
            for doc in data:
                match = True
                for k, v in query.items():
                    if k == "_id":
                        if str(doc.get("_id")) != str(v):
                            match = False
                            break
                    elif doc.get(k) != v:
                        match = False
                        break
                if match:
                    count += 1
            return count

    async def update_one(self, query: dict, update: dict) -> Any:
        async with self._lock:
            data = self._read_data()
            for doc in data:
                match = True
                for k, v in query.items():
                    if k == "_id":
                        if str(doc.get("_id")) != str(v):
                            match = False
                            break
                    elif doc.get(k) != v:
                        match = False
                        break
                if match:
                    if "$set" in update:
                        for uk, uv in update["$set"].items():
                            doc[uk] = uv
                    if "$inc" in update:
                        for uk, uv in update["$inc"].items():
                            doc[uk] = doc.get(uk, 0) + uv
                    self._write_data(data)
                    break


# Global collection references
users_collection = None
documents_collection = None
using_mock_db = False

async def init_database():
    global users_collection, documents_collection, using_mock_db
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=1000)
        await client.admin.command("ping")
        db = client[settings.MONGODB_DB_NAME]
        
        users_collection = db["users"]
        await users_collection.create_index("email", unique=True)
        
        documents_collection = db["documents"]
        await documents_collection.create_index("file_id", unique=True)
        await documents_collection.create_index("user_id")
        
        using_mock_db = False
        logger.info(f"Connected to live MongoDB at {settings.MONGODB_URL} (db: {settings.MONGODB_DB_NAME})")
    except Exception as e:
        logger.warning(f"MongoDB not available ({e}). Falling back to local Mongo-compatible JSON repository.")
        users_collection = LocalJsonMongoCollection("users_local_db.json")
        documents_collection = LocalJsonMongoCollection("documents_local_db.json")
        using_mock_db = True

def get_users_collection():
    global users_collection
    if users_collection is None:
        users_collection = LocalJsonMongoCollection("users_local_db.json")
    return users_collection

def get_documents_collection():
    global documents_collection
    if documents_collection is None:
        documents_collection = LocalJsonMongoCollection("documents_local_db.json")
    return documents_collection

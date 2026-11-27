import json
import time
import threading
from typing import Optional, Dict, Any
from app.config import settings

class InMemoryRedisFallback:
    """Thread-safe in-memory key-value store with TTL fallback when Redis service is offline."""
    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}
        self._locks: Dict[str, float] = {}
        self._lock = threading.Lock()

    def set(self, key: str, value: str, ex: Optional[int] = None):
        with self._lock:
            self._store[key] = value
            if ex:
                self._expiry[key] = time.time() + ex
            elif key in self._expiry:
                del self._expiry[key]

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            if key in self._expiry and time.time() > self._expiry[key]:
                del self._store[key]
                del self._expiry[key]
                return None
            return self._store.get(key)

    def delete(self, key: str):
        with self._lock:
            self._store.pop(key, None)
            self._expiry.pop(key, None)

    def acquire_lock(self, key: str, timeout: int = 30) -> bool:
        with self._lock:
            now = time.time()
            if key in self._locks and now < self._locks[key]:
                return False # Lock is still held
            self._locks[key] = now + timeout
            return True

    def release_lock(self, key: str):
        with self._lock:
            self._locks.pop(key, None)

class ShortTermMemory:
    """Short-term ephemeral memory and locking layer backed by Redis, with in-process fallback."""
    def __init__(self):
        self._redis = None
        self._fallback = InMemoryRedisFallback()
        self._using_fallback = False

        if not settings.USE_REDIS_FALLBACK:
            try:
                import redis
                client = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=1.0)
                client.ping()
                self._redis = client
            except Exception as e:
                # Log warning and fall back
                print(f"[ShortTermMemory] Redis connection failed ({e}). Using thread-safe in-memory fallback.")
                self._using_fallback = True
        else:
            self._using_fallback = True

    def save_scratchpad(self, run_id: str, data: Dict[str, Any], ttl_seconds: int = 3600):
        key = f"agent:scratchpad:{run_id}"
        payload = json.dumps(data)
        if not self._using_fallback and self._redis:
            try:
                self._redis.set(key, payload, ex=ttl_seconds)
                return
            except Exception:
                pass
        self._fallback.set(key, payload, ex=ttl_seconds)

    def get_scratchpad(self, run_id: str) -> Optional[Dict[str, Any]]:
        key = f"agent:scratchpad:{run_id}"
        val = None
        if not self._using_fallback and self._redis:
            try:
                val = self._redis.get(key)
            except Exception:
                val = None
        if val is None:
            val = self._fallback.get(key)
        
        if val:
            try:
                return json.loads(val)
            except Exception:
                return None
        return None

    def acquire_run_lock(self, run_id: str, timeout_seconds: int = 60) -> bool:
        lock_key = f"agent:lock:{run_id}"
        if not self._using_fallback and self._redis:
            try:
                # Redis atomic SET NX
                acquired = self._redis.set(lock_key, "locked", nx=True, ex=timeout_seconds)
                if acquired:
                    return True
                return False
            except Exception:
                pass
        return self._fallback.acquire_lock(lock_key, timeout=timeout_seconds)

    def release_run_lock(self, run_id: str):
        lock_key = f"agent:lock:{run_id}"
        if not self._using_fallback and self._redis:
            try:
                self._redis.delete(lock_key)
            except Exception:
                pass
        self._fallback.release_lock(lock_key)

    def clear(self, run_id: str):
        key = f"agent:scratchpad:{run_id}"
        if not self._using_fallback and self._redis:
            try:
                self._redis.delete(key)
            except Exception:
                pass
        self._fallback.delete(key)

short_term_memory = ShortTermMemory()

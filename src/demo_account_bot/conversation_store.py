from __future__ import annotations

import threading
import time
from collections.abc import Callable

from .domain import Conversation


class InMemoryConversationStore:
    def __init__(self, ttl_seconds: int, clock: Callable[[], float] = time.time) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._items: dict[tuple[str, str], Conversation] = {}
        self._lock = threading.RLock()

    def get(self, chat_id: str, open_id: str) -> Conversation | None:
        key = (chat_id, open_id)
        with self._lock:
            item = self._items.get(key)
            if item and self._clock() - item.updated_at >= self._ttl_seconds:
                self._delete_unlocked(key)
                return None
            return item

    def put(self, conversation: Conversation) -> None:
        with self._lock:
            conversation.updated_at = self._clock()
            self._items[conversation.key] = conversation

    def delete(self, chat_id: str, open_id: str) -> None:
        with self._lock:
            self._delete_unlocked((chat_id, open_id))

    def cleanup_expired(self) -> int:
        now = self._clock()
        with self._lock:
            expired = [
                key
                for key, item in self._items.items()
                if now - item.updated_at >= self._ttl_seconds
            ]
            for key in expired:
                self._delete_unlocked(key)
            return len(expired)

    def _delete_unlocked(self, key: tuple[str, str]) -> None:
        item = self._items.pop(key, None)
        if item:
            item.password = None


class MessageDeduplicator:
    def __init__(
        self,
        ttl_seconds: int = 12 * 60 * 60,
        max_entries: int = 5000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def first_seen(self, message_id: str) -> bool:
        if not message_id:
            return True
        now = self._clock()
        with self._lock:
            cutoff = now - self._ttl_seconds
            self._seen = {key: value for key, value in self._seen.items() if value >= cutoff}
            if message_id in self._seen:
                return False
            if len(self._seen) >= self._max_entries:
                oldest = min(self._seen, key=self._seen.__getitem__)
                self._seen.pop(oldest, None)
            self._seen[message_id] = now
            return True

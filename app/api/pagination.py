"""Cursor pagination helpers shared by API routes."""

import base64
import json
from datetime import datetime
from typing import Generic, TypeVar

from bson import ObjectId
from pydantic import BaseModel

T = TypeVar("T")


class CursorPage(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False


def encode_cursor(item: object, sort_field: str) -> str:
    sort_value = getattr(item, sort_field)
    payload = {
        sort_field: sort_value.isoformat(),
        "id": str(getattr(item, "id")),
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(cursor: str, sort_field: str) -> tuple[datetime, ObjectId]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return datetime.fromisoformat(payload[sort_field]), ObjectId(payload["id"])
    except Exception as exc:
        raise ValueError("Invalid cursor") from exc


def add_cursor_filter(filters: dict, cursor: str | None, sort_field: str) -> None:
    if not cursor:
        return

    cursor_value, cursor_id = decode_cursor(cursor, sort_field)
    cursor_filter = {
        "$or": [
            {sort_field: {"$lt": cursor_value}},
            {
                sort_field: cursor_value,
                "_id": {"$lt": cursor_id},
            },
        ],
    }
    filters.setdefault("$and", []).append(cursor_filter)


def build_cursor_page(items: list[T], limit: int, sort_field: str) -> CursorPage[T]:
    has_more = len(items) > limit
    page_items = items[:limit]
    return CursorPage(
        items=page_items,
        next_cursor=encode_cursor(page_items[-1], sort_field) if has_more and page_items else None,
        has_more=has_more,
    )

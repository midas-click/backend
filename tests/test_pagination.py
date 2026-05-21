from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from bson import ObjectId

from app.api.pagination import add_cursor_filter, build_cursor_page, decode_cursor, encode_cursor


# Encodes and decodes a cursor without losing the sort timestamp or document id.
def test_cursor_round_trip_preserves_sort_value_and_id():
    item = SimpleNamespace(id=ObjectId(), updated_at=datetime.utcnow())

    cursor = encode_cursor(item, "updated_at")
    sort_value, item_id = decode_cursor(cursor, "updated_at")

    assert sort_value == item.updated_at
    assert item_id == item.id


# Rejects malformed cursors so API routes can return a clear bad-request error.
def test_decode_cursor_rejects_invalid_payload():
    with pytest.raises(ValueError, match="Invalid cursor"):
        decode_cursor("not-a-valid-cursor", "updated_at")


# Adds the expected keyset pagination filter for descending timestamp/id ordering.
def test_add_cursor_filter_appends_keyset_filter():
    item = SimpleNamespace(id=ObjectId(), updated_at=datetime.utcnow())
    filters = {"org_id": "org_1"}

    add_cursor_filter(filters, encode_cursor(item, "updated_at"), "updated_at")

    assert filters["org_id"] == "org_1"
    assert filters["$and"][0] == {
        "$or": [
            {"updated_at": {"$lt": item.updated_at}},
            {"updated_at": item.updated_at, "_id": {"$lt": item.id}},
        ],
    }


# Returns a next cursor only when one extra item proves another page exists.
def test_build_cursor_page_trims_extra_item_and_sets_next_cursor():
    first = SimpleNamespace(id=ObjectId(), created_at=datetime.utcnow())
    second = SimpleNamespace(id=ObjectId(), created_at=datetime.utcnow() - timedelta(minutes=1))

    page = build_cursor_page([first, second], limit=1, sort_field="created_at")

    assert page.items == [first]
    assert page.has_more is True
    assert page.next_cursor == encode_cursor(first, "created_at")


# Leaves next cursor empty on the last page.
def test_build_cursor_page_has_no_cursor_when_page_is_complete():
    item = SimpleNamespace(id=ObjectId(), created_at=datetime.utcnow())

    page = build_cursor_page([item], limit=10, sort_field="created_at")

    assert page.items == [item]
    assert page.has_more is False
    assert page.next_cursor is None

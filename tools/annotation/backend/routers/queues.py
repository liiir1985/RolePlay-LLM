import json
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from database import get_conn


def _preview(raw: str | None, max_len: int = 100) -> str:
    if not raw:
        return ""
    try:
        obj = json.loads(raw)
        text = json.dumps(obj, ensure_ascii=False)
    except Exception:
        text = raw
    return text[:max_len]


router = APIRouter()


class QueueIn(BaseModel):
    name: str
    schema_id: int


class AddItemsIn(BaseModel):
    record_ids: List[str]


class AddAllItemsIn(BaseModel):
    search: str = ""
    start_time: str = ""
    end_time: str = ""


class AnnotateIn(BaseModel):
    values: dict


@router.get("")
def list_queues():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT q.*, s.name as schema_name,
                   COUNT(qi.id) as total_items,
                   SUM(CASE WHEN qi.status='annotated' THEN 1 ELSE 0 END) as annotated_items
            FROM queues q
            JOIN annotation_schemas s ON s.id = q.schema_id
            LEFT JOIN queue_items qi ON qi.queue_id = q.id
            GROUP BY q.id ORDER BY q.created_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_queue(body: QueueIn):
    with get_conn() as conn:
        schema = conn.execute("SELECT id FROM annotation_schemas WHERE id=?", (body.schema_id,)).fetchone()
        if not schema:
            raise HTTPException(404, "Schema not found")
        try:
            cur = conn.execute("INSERT INTO queues (name, schema_id) VALUES (?,?)", (body.name, body.schema_id))
            queue_id = cur.lastrowid
        except Exception:
            raise HTTPException(409, "Queue name already exists")
        row = conn.execute("SELECT * FROM queues WHERE id=?", (queue_id,)).fetchone()
    return dict(row)


@router.get("/{queue_id}")
def get_queue(queue_id: int):
    with get_conn() as conn:
        row = conn.execute("""
            SELECT q.*, s.name as schema_name
            FROM queues q JOIN annotation_schemas s ON s.id=q.schema_id
            WHERE q.id=?
        """, (queue_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Queue not found")
        fields = conn.execute(
            "SELECT * FROM schema_fields WHERE schema_id=? ORDER BY order_idx", (row["schema_id"],)
        ).fetchall()
    result = dict(row)
    result["fields"] = [
        {**dict(f), "options": json.loads(f["options"]) if f["options"] else None}
        for f in fields
    ]
    return result


@router.delete("/{queue_id}", status_code=204)
def delete_queue(queue_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM queues WHERE id=?", (queue_id,))


@router.post("/{queue_id}/items", status_code=201)
def add_items(queue_id: int, body: AddItemsIn):
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM queues WHERE id=?", (queue_id,)).fetchone():
            raise HTTPException(404, "Queue not found")
        added = 0
        for rid in body.record_ids:
            try:
                conn.execute("INSERT INTO queue_items (queue_id, record_id) VALUES (?,?)", (queue_id, rid))
                added += 1
            except Exception:
                pass
    return {"added": added}


@router.post("/{queue_id}/items/all", status_code=201)
def add_all_items(queue_id: int, body: AddAllItemsIn):
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM queues WHERE id=?", (queue_id,)).fetchone():
            raise HTTPException(404, "Queue not found")
        where_clauses = []
        params: list = []
        if body.search:
            pattern = f"%{body.search}%"
            where_clauses.append("(id LIKE ? OR name LIKE ?)")
            params += [pattern, pattern]
        if body.start_time:
            where_clauses.append("timestamp >= ?")
            params.append(body.start_time)
        if body.end_time:
            where_clauses.append("timestamp <= ?")
            params.append(body.end_time)
        where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        rows = conn.execute(f"SELECT id FROM records {where}", params).fetchall()
        added = 0
        for r in rows:
            try:
                conn.execute("INSERT INTO queue_items (queue_id, record_id) VALUES (?,?)", (queue_id, r["id"]))
                added += 1
            except Exception:
                pass
    return {"added": added}


@router.get("/{queue_id}/item-ids")
def list_item_ids(queue_id: int):
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM queues WHERE id=?", (queue_id,)).fetchone():
            raise HTTPException(404, "Queue not found")
        rows = conn.execute(
            "SELECT id FROM queue_items WHERE queue_id=? ORDER BY id", (queue_id,)
        ).fetchall()
    return [r["id"] for r in rows]


@router.get("/{queue_id}/items")
def list_items(
    queue_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    status: str = Query(""),
    start_time: str = Query(""),
    end_time: str = Query(""),
):
    offset = (page - 1) * limit
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM queues WHERE id=?", (queue_id,)).fetchone():
            raise HTTPException(404, "Queue not found")
        base = "FROM queue_items qi JOIN records r ON r.id=qi.record_id WHERE qi.queue_id=?"
        params: list = [queue_id]
        if status in ("pending", "annotated"):
            base += " AND qi.status=?"
            params.append(status)
        if start_time:
            base += " AND r.timestamp >= ?"
            params.append(start_time)
        if end_time:
            base += " AND r.timestamp <= ?"
            params.append(end_time)
        total = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT qi.id, qi.record_id, qi.status, qi.created_at, r.timestamp, r.input, r.output {base} ORDER BY qi.id LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    items = [
        {
            "id": r["id"], "record_id": r["record_id"], "status": r["status"],
            "timestamp": r["timestamp"],
            "input_preview": _preview(r["input"]),
            "output_preview": _preview(r["output"]),
        }
        for r in rows
    ]
    return {"total": total, "page": page, "limit": limit, "items": items}


@router.get("/{queue_id}/items/{item_id}")
def get_item(queue_id: int, item_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT qi.*, r.input, r.output, r.metadata, r.name as record_name, r.type as record_type, r.timestamp FROM queue_items qi JOIN records r ON r.id=qi.record_id WHERE qi.id=? AND qi.queue_id=?",
            (item_id, queue_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Item not found")
        ann = conn.execute('SELECT "values" FROM annotations WHERE queue_item_id=?', (item_id,)).fetchone()
    result = dict(row)
    result["annotation"] = json.loads(ann["values"]) if ann else None
    return result


@router.post("/{queue_id}/items/{item_id}/annotate")
def annotate_item(queue_id: int, item_id: int, body: AnnotateIn):
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM queue_items WHERE id=? AND queue_id=?", (item_id, queue_id)).fetchone()
        if not row:
            raise HTTPException(404, "Item not found")
        values_json = json.dumps(body.values, ensure_ascii=False)
        conn.execute(
            'INSERT INTO annotations (queue_item_id, "values", updated_at) VALUES (?,?,datetime(\'now\')) ON CONFLICT(queue_item_id) DO UPDATE SET "values"=excluded."values", updated_at=excluded.updated_at',
            (item_id, values_json),
        )
        conn.execute("UPDATE queue_items SET status='annotated' WHERE id=?", (item_id,))
    return {"ok": True}

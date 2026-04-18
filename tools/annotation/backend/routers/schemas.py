import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from database import get_conn

router = APIRouter()


class FieldIn(BaseModel):
    name: str
    label: str
    type: str  # number|category|text|boolean|score
    options: Optional[List[str]] = None
    order_idx: int = 0


class SchemaIn(BaseModel):
    name: str
    fields: List[FieldIn] = []


def _schema_with_fields(conn, schema_id: int):
    schema = conn.execute("SELECT * FROM annotation_schemas WHERE id=?", (schema_id,)).fetchone()
    if not schema:
        return None
    fields = conn.execute(
        "SELECT * FROM schema_fields WHERE schema_id=? ORDER BY order_idx", (schema_id,)
    ).fetchall()
    result = dict(schema)
    result["fields"] = [
        {**dict(f), "options": json.loads(f["options"]) if f["options"] else None}
        for f in fields
    ]
    return result


@router.get("")
def list_schemas():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM annotation_schemas ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_schema(body: SchemaIn):
    with get_conn() as conn:
        try:
            cur = conn.execute("INSERT INTO annotation_schemas (name) VALUES (?)", (body.name,))
            schema_id = cur.lastrowid
        except Exception:
            raise HTTPException(409, "Schema name already exists")
        for f in body.fields:
            conn.execute(
                "INSERT INTO schema_fields (schema_id, name, label, type, options, order_idx) VALUES (?,?,?,?,?,?)",
                (schema_id, f.name, f.label, f.type, json.dumps(f.options) if f.options else None, f.order_idx),
            )
        return _schema_with_fields(conn, schema_id)


@router.get("/{schema_id}")
def get_schema(schema_id: int):
    with get_conn() as conn:
        result = _schema_with_fields(conn, schema_id)
    if not result:
        raise HTTPException(404, "Schema not found")
    return result


@router.put("/{schema_id}")
def update_schema(schema_id: int, body: SchemaIn):
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM annotation_schemas WHERE id=?", (schema_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Schema not found")
        conn.execute("UPDATE annotation_schemas SET name=? WHERE id=?", (body.name, schema_id))
        conn.execute("DELETE FROM schema_fields WHERE schema_id=?", (schema_id,))
        for f in body.fields:
            conn.execute(
                "INSERT INTO schema_fields (schema_id, name, label, type, options, order_idx) VALUES (?,?,?,?,?,?)",
                (schema_id, f.name, f.label, f.type, json.dumps(f.options) if f.options else None, f.order_idx),
            )
        return _schema_with_fields(conn, schema_id)


@router.delete("/{schema_id}", status_code=204)
def delete_schema(schema_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM annotation_schemas WHERE id=?", (schema_id,))

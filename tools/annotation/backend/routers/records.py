import json
from fastapi import APIRouter, UploadFile, File, HTTPException, Query

from database import get_conn

router = APIRouter()


@router.post("/import")
async def import_records(file: UploadFile = File(...)):
    content = await file.read()
    lines = content.decode("utf-8").splitlines()
    inserted = 0
    skipped = 0
    with get_conn() as conn:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO records
                       (id, type, name, timestamp, depth, input, output, metadata)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        obj.get("id", ""),
                        obj.get("type"),
                        obj.get("name"),
                        obj.get("timestamp") or obj.get("startTime"),
                        obj.get("depth"),
                        obj.get("input") if isinstance(obj.get("input"), str) else json.dumps(obj.get("input")),
                        obj.get("output") if isinstance(obj.get("output"), str) else json.dumps(obj.get("output")),
                        obj.get("metadata") if isinstance(obj.get("metadata"), str) else json.dumps(obj.get("metadata")),
                    ),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    inserted += 1
                else:
                    skipped += 1
            except Exception:
                skipped += 1
    return {"inserted": inserted, "skipped": skipped}


def _preview(raw: str | None, max_len: int = 100) -> str:
    if not raw:
        return ""
    try:
        obj = json.loads(raw)
        text = json.dumps(obj, ensure_ascii=False)
    except Exception:
        text = raw
    return text[:max_len]


@router.get("")
def list_records(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: str = Query(""),
    start_time: str = Query(""),
    end_time: str = Query(""),
):
    offset = (page - 1) * limit
    where_clauses = []
    params: list = []
    if search:
        pattern = f"%{search}%"
        where_clauses.append("(id LIKE ? OR name LIKE ?)")
        params += [pattern, pattern]
    if start_time:
        where_clauses.append("timestamp >= ?")
        params.append(start_time)
    if end_time:
        where_clauses.append("timestamp <= ?")
        params.append(end_time)
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM records {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT id, timestamp, input, output FROM records {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    items = [
        {"id": r["id"], "timestamp": r["timestamp"], "input_preview": _preview(r["input"]), "output_preview": _preview(r["output"])}
        for r in rows
    ]
    return {"total": total, "page": page, "limit": limit, "items": items}


@router.get("/{record_id}")
def get_record(record_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Record not found")
    return dict(row)

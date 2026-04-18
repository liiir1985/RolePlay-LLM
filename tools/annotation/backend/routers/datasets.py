import json
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
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


class DatasetIn(BaseModel):
    name: str


class AddRawIn(BaseModel):
    record_ids: List[str]


class AddAnnotatedIn(BaseModel):
    queue_item_ids: List[int]


@router.get("")
def list_datasets():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT d.*, COUNT(di.id) as item_count
            FROM datasets d LEFT JOIN dataset_items di ON di.dataset_id=d.id
            GROUP BY d.id ORDER BY d.created_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_dataset(body: DatasetIn):
    with get_conn() as conn:
        try:
            cur = conn.execute("INSERT INTO datasets (name) VALUES (?)", (body.name,))
            row = conn.execute("SELECT * FROM datasets WHERE id=?", (cur.lastrowid,)).fetchone()
        except Exception:
            raise HTTPException(409, "Dataset name already exists")
    return dict(row)


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM datasets WHERE id=?", (dataset_id,))


@router.post("/{dataset_id}/items/raw", status_code=201)
def add_raw_items(dataset_id: int, body: AddRawIn):
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM datasets WHERE id=?", (dataset_id,)).fetchone():
            raise HTTPException(404, "Dataset not found")
        added, dupes = 0, 0
        for rid in body.record_ids:
            try:
                conn.execute(
                    "INSERT INTO dataset_items (dataset_id, record_id, source) VALUES (?,?,?)",
                    (dataset_id, rid, "raw"),
                )
                added += 1
            except Exception:
                dupes += 1
    return {"added": added, "duplicates": dupes}


@router.post("/{dataset_id}/items/annotated", status_code=201)
def add_annotated_items(dataset_id: int, body: AddAnnotatedIn):
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM datasets WHERE id=?", (dataset_id,)).fetchone():
            raise HTTPException(404, "Dataset not found")
        added, dupes, skipped = 0, 0, 0
        for qiid in body.queue_item_ids:
            qi = conn.execute(
                "SELECT record_id, status FROM queue_items WHERE id=?", (qiid,)
            ).fetchone()
            if not qi or qi["status"] != "annotated":
                skipped += 1
                continue
            try:
                conn.execute(
                    "INSERT INTO dataset_items (dataset_id, record_id, source, queue_item_id) VALUES (?,?,?,?)",
                    (dataset_id, qi["record_id"], "annotated", qiid),
                )
                added += 1
            except Exception:
                dupes += 1
    return {"added": added, "duplicates": dupes, "skipped": skipped}


@router.get("/{dataset_id}/items")
def list_items(
    dataset_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    source: str = Query(""),
    start_time: str = Query(""),
    end_time: str = Query(""),
    ann_filter: str = Query(""),
):
    offset = (page - 1) * limit
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM datasets WHERE id=?", (dataset_id,)).fetchone():
            raise HTTPException(404, "Dataset not found")
        base = "FROM dataset_items di JOIN records r ON r.id=di.record_id LEFT JOIN annotations a ON a.queue_item_id=di.queue_item_id WHERE di.dataset_id=?"
        params: list = [dataset_id]
        if source in ("raw", "annotated"):
            base += " AND di.source=?"
            params.append(source)
        if start_time:
            base += " AND r.timestamp >= ?"
            params.append(start_time)
        if end_time:
            base += " AND r.timestamp <= ?"
            params.append(end_time)
        if ann_filter:
            base += ' AND a."values" LIKE ?'
            params.append(f"%{ann_filter}%")
        total = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
        rows = conn.execute(
            f'SELECT di.id, di.record_id, di.source, di.queue_item_id, r.timestamp, r.input, r.output, a."values" as ann_values {base} ORDER BY di.id LIMIT ? OFFSET ?',
            params + [limit, offset],
        ).fetchall()
    items = []
    for r in rows:
        item: dict = {
            "id": r["id"], "record_id": r["record_id"], "source": r["source"],
            "timestamp": r["timestamp"],
            "input_preview": _preview(r["input"]),
            "output_preview": _preview(r["output"]),
            "annotations": json.loads(r["ann_values"]) if r["ann_values"] else None,
        }
        items.append(item)
    return {"total": total, "page": page, "limit": limit, "items": items}


@router.delete("/{dataset_id}/items/{item_id}", status_code=204)
def remove_item(dataset_id: int, item_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM dataset_items WHERE id=? AND dataset_id=?", (item_id, dataset_id))


@router.get("/{dataset_id}/export")
def export_dataset(dataset_id: int):
    with get_conn() as conn:
        ds = conn.execute("SELECT name FROM datasets WHERE id=?", (dataset_id,)).fetchone()
        if not ds:
            raise HTTPException(404, "Dataset not found")
        ds_name = ds["name"]
        items = conn.execute(
            "SELECT di.source, di.queue_item_id, r.input, r.output, r.metadata FROM dataset_items di JOIN records r ON r.id=di.record_id WHERE di.dataset_id=?",
            (dataset_id,),
        ).fetchall()
        ann_map = {}
        for item in items:
            if item["queue_item_id"]:
                ann = conn.execute('SELECT "values" FROM annotations WHERE queue_item_id=?', (item["queue_item_id"],)).fetchone()
                if ann:
                    ann_map[item["queue_item_id"]] = json.loads(ann["values"])

    def generate():
        for item in items:
            try:
                inp = json.loads(item["input"]) if item["input"] else {}
                messages = inp.get("messages", [])
            except Exception:
                messages = []
            record: dict = {"messages": messages}
            if item["source"] == "annotated" and item["queue_item_id"] in ann_map:
                record["annotations"] = ann_map[item["queue_item_id"]]
            try:
                meta = json.loads(item["metadata"]) if item["metadata"] else {}
            except Exception:
                meta = {}
            if meta:
                record["metadata"] = meta
            yield json.dumps(record, ensure_ascii=False) + "\n"

    filename = ds_name.replace(" ", "_") + ".jsonl"
    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

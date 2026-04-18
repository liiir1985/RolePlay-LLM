import json
from datetime import datetime
from difflib import SequenceMatcher
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

from database import get_conn

router = APIRouter()


def extract_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif item.get("type") == "tool_use":
                    pass
                elif item.get("type") == "tool_result":
                    parts.append(str(item.get("content", "")))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content)


def extract_tool_call_ids(output: dict) -> list:
    tool_calls = output.get("tool_calls")
    if not tool_calls:
        return []
    return [tc["id"] for tc in tool_calls if isinstance(tc, dict) and "id" in tc]


def find_tool_use_ids_in_content(content) -> list:
    if not isinstance(content, list):
        return []
    return [item["id"] for item in content if isinstance(item, dict) and item.get("type") == "tool_use" and "id" in item]


def text_similarity(a: str, b: str) -> float:
    if not a:
        return 1.0
    if not b:
        return 0.0
    if len(a) > 5000 or len(b) > 5000:
        a_sample = a[:2000] + a[-2000:] if len(a) > 4000 else a
        b_sample = b[:2000] + b[-2000:] if len(b) > 4000 else b
        return SequenceMatcher(None, a_sample, b_sample).ratio()
    return SequenceMatcher(None, a, b).ratio()


def parse_record(row) -> Optional[dict]:
    try:
        inp = json.loads(row["input"]) if row["input"] else {}
    except (json.JSONDecodeError, TypeError):
        return None
    try:
        out = json.loads(row["output"]) if row["output"] else {}
    except (json.JSONDecodeError, TypeError):
        out = {}
    if not isinstance(inp, dict):
        return None
    messages = inp.get("messages", [])
    if not messages:
        return None
    if not isinstance(out, dict):
        out = {}
    return {
        "id": row["id"],
        "timestamp": row["timestamp"] or "",
        "msg_count": len(messages),
        "messages": messages,
        "output": out,
        "metadata": row["metadata"],
    }


def check_output_in_messages(a_output: dict, b_messages: list) -> bool:
    a_content = a_output.get("content")
    a_tool_ids = extract_tool_call_ids(a_output)

    if a_tool_ids:
        for msg in b_messages:
            if msg.get("role") != "assistant":
                continue
            msg_content = msg.get("content")
            tool_ids_in_msg = find_tool_use_ids_in_content(msg_content)
            if tool_ids_in_msg:
                matched = sum(1 for tid in a_tool_ids if tid in tool_ids_in_msg)
                if matched >= len(a_tool_ids) * 0.5:
                    return True

    if a_content:
        a_text = extract_text(a_content).strip()
        if not a_text:
            return False
        for msg in b_messages:
            if msg.get("role") != "assistant":
                continue
            b_text = extract_text(msg.get("content")).strip()
            if not b_text:
                continue
            if len(a_text) < 20:
                if a_text in b_text:
                    return True
                continue
            sim = text_similarity(a_text, b_text)
            if sim >= 0.9:
                return True
            if len(a_text) > len(b_text):
                sim2 = text_similarity(b_text, a_text)
                if sim2 >= 0.9:
                    return True

    return False


def detect_chains(records: list) -> list:
    n = len(records)
    next_map = {}
    prev_map = {}

    for i in range(n):
        a = records[i]
        a_out = a["output"]
        if not a_out.get("content") and not extract_tool_call_ids(a_out):
            continue
        for j in range(i + 1, min(i + 50, n)):
            b = records[j]
            if check_output_in_messages(a_out, b["messages"]):
                if b["id"] not in prev_map:
                    next_map[a["id"]] = b["id"]
                    prev_map[b["id"]] = a["id"]
                break
            if b["timestamp"] and a["timestamp"]:
                try:
                    ta = datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00"))
                    tb = datetime.fromisoformat(b["timestamp"].replace("Z", "+00:00"))
                    if (tb - ta).total_seconds() > 7200:
                        break
                except:
                    pass

    chains = []
    visited = set()
    id_to_record = {r["id"]: r for r in records}

    for r in records:
        rid = r["id"]
        if rid in visited:
            continue
        if rid in prev_map:
            continue
        chain = [rid]
        visited.add(rid)
        current = rid
        while current in next_map:
            nxt = next_map[current]
            chain.append(nxt)
            visited.add(nxt)
            current = nxt
        if len(chain) > 1:
            chains.append([id_to_record[cid] for cid in chain])

    return chains


def detect_chains_streaming(records: list):
    """Generator that yields SSE progress events, then yields the final chains list as last item."""
    n = len(records)
    next_map = {}
    prev_map = {}

    for i in range(n):
        a = records[i]
        a_out = a["output"]
        if not a_out.get("content") and not extract_tool_call_ids(a_out):
            if (i + 1) % 100 == 0:
                yield f"data: {json.dumps({'stage': 'detecting', 'progress': i + 1, 'total': n, 'message': f'检测会话链 {i+1}/{n}'})}\n\n"
            continue
        for j in range(i + 1, min(i + 50, n)):
            b = records[j]
            if check_output_in_messages(a_out, b["messages"]):
                if b["id"] not in prev_map:
                    next_map[a["id"]] = b["id"]
                    prev_map[b["id"]] = a["id"]
                break
            if b["timestamp"] and a["timestamp"]:
                try:
                    ta = datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00"))
                    tb = datetime.fromisoformat(b["timestamp"].replace("Z", "+00:00"))
                    if (tb - ta).total_seconds() > 7200:
                        break
                except:
                    pass
        # Yield progress after every record that required comparison
        yield f"data: {json.dumps({'stage': 'detecting', 'progress': i + 1, 'total': n, 'message': f'检测会话链 {i+1}/{n}'})}\n\n"

    chains = []
    visited = set()
    id_to_record = {r["id"]: r for r in records}

    for r in records:
        rid = r["id"]
        if rid in visited:
            continue
        if rid in prev_map:
            continue
        chain = [rid]
        visited.add(rid)
        current = rid
        while current in next_map:
            nxt = next_map[current]
            chain.append(nxt)
            visited.add(nxt)
            current = nxt
        if len(chain) > 1:
            chains.append([id_to_record[cid] for cid in chain])

    yield chains


def compute_merged(chain: list) -> dict:
    first = chain[0]
    last = chain[-1]

    # Build the final messages from the last record's input + output
    final_messages = list(last["messages"])

    # Append last record's output as the final assistant turn
    last_out = last["output"]
    last_content = last_out.get("content")
    last_tool_calls = last_out.get("tool_calls")

    if last_content or last_tool_calls:
        assistant_msg = {"role": "assistant"}
        if last_tool_calls:
            # Convert to content block format for consistency
            blocks = []
            if last_content:
                blocks.append({"type": "text", "text": last_content})
            for tc in last_tool_calls:
                func = tc.get("function", {})
                try:
                    inp = json.loads(func.get("arguments", "{}"))
                except:
                    inp = func.get("arguments", "")
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": func.get("name", ""),
                    "input": inp,
                })
            assistant_msg["content"] = blocks
        else:
            assistant_msg["content"] = last_content
        final_messages.append(assistant_msg)

    # Replace stripped versions with full originals from chain records
    for rec in chain[:-1]:
        rec_out = rec["output"]
        rec_content = rec_out.get("content")
        rec_tool_ids = extract_tool_call_ids(rec_out)

        if rec_tool_ids:
            for idx, msg in enumerate(final_messages):
                if msg.get("role") != "assistant":
                    continue
                msg_tool_ids = find_tool_use_ids_in_content(msg.get("content"))
                if msg_tool_ids:
                    matched = sum(1 for tid in rec_tool_ids if tid in msg_tool_ids)
                    if matched >= len(rec_tool_ids) * 0.5:
                        # Merge: keep the version with more info
                        existing_content = msg.get("content", [])
                        if isinstance(existing_content, list):
                            # Already in block format, keep as-is (input version has tool_result context)
                            pass
                        break

        elif rec_content:
            rec_text = extract_text(rec_content).strip()
            if not rec_text:
                continue
            for idx, msg in enumerate(final_messages):
                if msg.get("role") != "assistant":
                    continue
                msg_text = extract_text(msg.get("content")).strip()
                if not msg_text:
                    continue
                sim = text_similarity(msg_text, rec_text)
                if sim >= 0.9:
                    # Replace with longer version
                    if len(rec_text) > len(msg_text):
                        final_messages[idx] = {"role": "assistant", "content": rec_content}
                    break

    return {
        "id": first["id"],
        "messages": final_messages,
        "output": last["output"],
        "metadata": first.get("metadata"),
        "timestamp": first["timestamp"],
    }


@router.post("/merge-preview")
def merge_preview():
    def generate():
        with get_conn() as conn:
            total_count = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
            yield f"data: {json.dumps({'stage': 'loading', 'progress': 0, 'total': total_count, 'message': '正在加载记录...'})}\n\n"

            rows = conn.execute(
                "SELECT id, timestamp, input, output, metadata FROM records ORDER BY timestamp ASC, id ASC"
            ).fetchall()

        records = []
        for i, row in enumerate(rows):
            parsed = parse_record(row)
            if parsed:
                records.append(parsed)
            if (i + 1) % 100 == 0 or i == len(rows) - 1:
                yield f"data: {json.dumps({'stage': 'parsing', 'progress': i + 1, 'total': len(rows), 'message': f'解析记录 {i+1}/{len(rows)}'})}\n\n"

        yield f"data: {json.dumps({'stage': 'detecting', 'progress': 0, 'total': len(records), 'message': '正在检测会话链...'})}\n\n"

        chains = None
        for item in detect_chains_streaming(records):
            if isinstance(item, str):
                yield item
            else:
                chains = item

        result_chains = []
        for i, chain in enumerate(chains):
            result_chains.append({
                "index": i,
                "records": [{"id": r["id"], "timestamp": r["timestamp"], "msg_count": r["msg_count"]} for r in chain],
                "surviving_id": chain[0]["id"],
                "delete_count": len(chain) - 1,
            })

        yield f"data: {json.dumps({'stage': 'done', 'result': {'chains': result_chains, 'total_chains': len(chains), 'total_mergeable': sum(len(c) for c in chains)}})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


class MergeExecuteIn(BaseModel):
    # Each item is a list of record IDs forming one chain (first ID is the surviving record)
    chains: List[List[str]]


@router.post("/merge-execute")
def merge_execute(body: MergeExecuteIn):
    def generate():
        if not body.chains:
            yield f"data: {json.dumps({'stage': 'error', 'message': '没有有效的会话链'})}\n\n"
            return

        # Collect all needed record IDs
        all_ids = list({rid for chain in body.chains for rid in chain})
        placeholders = ",".join("?" * len(all_ids))

        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT id, timestamp, input, output, metadata FROM records WHERE id IN ({placeholders})",
                all_ids,
            ).fetchall()

        id_to_record = {}
        for row in rows:
            parsed = parse_record(row)
            if parsed:
                id_to_record[parsed["id"]] = parsed

        selected = []
        for chain_ids in body.chains:
            chain = [id_to_record[rid] for rid in chain_ids if rid in id_to_record]
            if len(chain) > 1:
                selected.append(chain)

        if not selected:
            yield f"data: {json.dumps({'stage': 'error', 'message': '没有有效的会话链'})}\n\n"
            return

        merged_count = 0
        deleted_count = 0
        total = len(selected)

        with get_conn() as conn:
            for ci, chain in enumerate(selected):
                merged = compute_merged(chain)
                surviving_id = merged["id"]
                delete_ids = [r["id"] for r in chain[1:]]

                new_input = json.dumps({"messages": merged["messages"]}, ensure_ascii=False)
                new_output = json.dumps(merged["output"], ensure_ascii=False) if merged["output"] else None
                conn.execute(
                    "UPDATE records SET input=?, output=? WHERE id=?",
                    (new_input, new_output, surviving_id),
                )

                for did in delete_ids:
                    try:
                        conn.execute(
                            "UPDATE queue_items SET record_id=? WHERE record_id=?",
                            (surviving_id, did),
                        )
                    except Exception:
                        conn.execute("DELETE FROM queue_items WHERE record_id=?", (did,))
                    try:
                        conn.execute(
                            "UPDATE dataset_items SET record_id=? WHERE record_id=?",
                            (surviving_id, did),
                        )
                    except Exception:
                        conn.execute("DELETE FROM dataset_items WHERE record_id=?", (did,))

                placeholders = ",".join("?" * len(delete_ids))
                conn.execute(f"DELETE FROM records WHERE id IN ({placeholders})", delete_ids)

                merged_count += 1
                deleted_count += len(delete_ids)
                yield f"data: {json.dumps({'stage': 'merging', 'progress': ci + 1, 'total': total, 'message': f'合并中 {ci+1}/{total}'})}\n\n"

        yield f"data: {json.dumps({'stage': 'done', 'result': {'merged': merged_count, 'deleted': deleted_count}})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

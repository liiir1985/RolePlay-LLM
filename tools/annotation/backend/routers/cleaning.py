import json
import re
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
    """Return how much of the shorter text is contained in the longer one."""
    if not a:
        return 1.0
    if not b:
        return 0.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) > 5000:
        shorter = shorter[:2000] + shorter[-2000:]
        longer = longer[:2000] + longer[-2000:]
    sm = SequenceMatcher(None, shorter, longer)
    matching = sum(block.size for block in sm.get_matching_blocks())
    return matching / len(shorter) if shorter else 0.0


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


_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


@router.post("/fix-json-strings")
def fix_json_strings():
    def generate():
        with get_conn() as conn:
            rows = conn.execute("SELECT id, input, output FROM records").fetchall()

        total = len(rows)
        yield f"data: {json.dumps({'stage': 'processing', 'progress': 0, 'total': total, 'message': f'共 {total} 条记录'})}\n\n"

        fixed = 0
        with get_conn() as conn:
            for i, row in enumerate(rows):
                new_input = row["input"]
                new_output = row["output"]
                changed = False

                for field, val in (("input", row["input"]), ("output", row["output"])):
                    if not isinstance(val, str):
                        continue

                    # Strip ANSI escape sequences
                    cleaned = _ANSI_RE.sub('', val)
                    if cleaned != val:
                        changed = True
                        val = cleaned

                    # Unwrap double-encoded JSON (json.loads -> str -> json.loads)
                    try:
                        parsed = json.loads(val, strict=False)
                        if isinstance(parsed, str):
                            try:
                                inner = json.loads(parsed, strict=False)
                                if isinstance(inner, (dict, list)):
                                    val = json.dumps(inner, ensure_ascii=False)
                                    changed = True
                            except (json.JSONDecodeError, ValueError):
                                pass
                        elif cleaned != row[field]:
                            val = json.dumps(parsed, ensure_ascii=False)
                    except (json.JSONDecodeError, ValueError):
                        pass

                    if field == "input":
                        new_input = val
                    else:
                        new_output = val

                if changed:
                    conn.execute(
                        "UPDATE records SET input=?, output=? WHERE id=?",
                        (new_input, new_output, row["id"]),
                    )
                    fixed += 1

                if (i + 1) % 200 == 0 or i == total - 1:
                    conn.commit()
                    yield f"data: {json.dumps({'stage': 'processing', 'progress': i + 1, 'total': total, 'message': f'处理中 {i+1}/{total}'})}\n\n"

        yield f"data: {json.dumps({'stage': 'done', 'result': {'fixed': fixed, 'total': total}})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


def _is_output_empty(output_str: str | None) -> bool:
    if not output_str:
        return True
    try:
        out = json.loads(output_str, strict=False)
    except (json.JSONDecodeError, ValueError):
        return not output_str.strip()
    if out is None:
        return True
    if isinstance(out, str):
        return not out.strip()
    if isinstance(out, dict):
        content = out.get("content")
        tool_calls = out.get("tool_calls")
        function_call = out.get("function_call")
        has_content = content and (content if isinstance(content, str) else any(
            b.get("text") or b.get("content") for b in content if isinstance(b, dict)
        ))
        has_tool = tool_calls and len(tool_calls) > 0
        has_func = function_call and isinstance(function_call, dict) and function_call.get("name")
        return not (has_content or has_tool or has_func)
    return False


def _has_assistant_content(input_str: str | None) -> bool:
    if not input_str:
        return False
    try:
        inp = json.loads(input_str, strict=False)
    except (json.JSONDecodeError, ValueError):
        return False
    if not isinstance(inp, dict):
        return False
    messages = inp.get("messages", [])
    if not isinstance(messages, list):
        return False
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if content is None or content == "":
            continue
        if isinstance(content, str) and content.strip():
            return True
        if isinstance(content, list) and any(
            (b.get("text") or "").strip() or b.get("type") == "tool_use"
            for b in content if isinstance(b, dict)
        ):
            return True
    return False


@router.post("/remove-empty-records")
def remove_empty_records():
    def generate():
        with get_conn() as conn:
            rows = conn.execute("SELECT id, input, output FROM records").fetchall()

        total = len(rows)
        yield f"data: {json.dumps({'stage': 'processing', 'progress': 0, 'total': total, 'message': f'共 {total} 条记录'})}\n\n"

        to_delete = []
        for i, row in enumerate(rows):
            if not _has_assistant_content(row["input"]) and _is_output_empty(row["output"]):
                to_delete.append(row["id"])
            if (i + 1) % 200 == 0 or i == total - 1:
                yield f"data: {json.dumps({'stage': 'processing', 'progress': i + 1, 'total': total, 'message': f'扫描中 {i+1}/{total}，待删除 {len(to_delete)}'})}\n\n"

        if not to_delete:
            yield f"data: {json.dumps({'stage': 'done', 'result': {'deleted': 0, 'total': total}})}\n\n"
            return

        with get_conn() as conn:
            batch_size = 100
            for start in range(0, len(to_delete), batch_size):
                batch = to_delete[start:start + batch_size]
                placeholders = ",".join("?" * len(batch))
                conn.execute(f"DELETE FROM queue_items WHERE record_id IN ({placeholders})", batch)
                conn.execute(f"DELETE FROM dataset_items WHERE record_id IN ({placeholders})", batch)
                conn.execute(f"DELETE FROM records WHERE id IN ({placeholders})", batch)
                conn.commit()
                yield f"data: {json.dumps({'stage': 'deleting', 'progress': min(start + batch_size, len(to_delete)), 'total': len(to_delete), 'message': f'删除中 {min(start + batch_size, len(to_delete))}/{len(to_delete)}'})}\n\n"

        yield f"data: {json.dumps({'stage': 'done', 'result': {'deleted': len(to_delete), 'total': total}})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


def _merge_intervals(intervals):
    if not intervals:
        return []
    intervals.sort()
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _find_repeated_intervals(text, reference_texts, min_len=10):
    intervals = []
    for ref in reference_texts:
        sm = SequenceMatcher(None, text, ref, autojunk=False)
        for block in sm.get_matching_blocks():
            if block.size >= min_len:
                intervals.append((block.a, block.a + block.size))
    return _merge_intervals(intervals)


def _remove_intervals(text, intervals):
    if not intervals:
        return text
    parts = []
    prev_end = 0
    for start, end in intervals:
        parts.append(text[prev_end:start])
        prev_end = end
    parts.append(text[prev_end:])
    return "".join(parts)


def _dedup_system_messages(messages):
    system_items = []
    for i, m in enumerate(messages):
        if m.get("role") == "system":
            system_items.append((i, extract_text(m.get("content"))))

    to_update = {}
    to_remove = set()

    for idx in range(len(system_items) - 1, -1, -1):
        pos, text = system_items[idx]
        if not text or len(text) < 10:
            continue
        earlier_texts = [t for _, t in system_items[:idx]]
        if not earlier_texts:
            continue
        intervals = _find_repeated_intervals(text, earlier_texts, min_len=10)
        if intervals:
            new_text = _remove_intervals(text, intervals).strip()
            if not new_text:
                to_remove.add(pos)
            else:
                to_update[pos] = new_text

    if not to_update and not to_remove:
        return messages, False

    new_messages = []
    for i, m in enumerate(messages):
        if i in to_remove:
            continue
        if i in to_update:
            m = dict(m)
            m["content"] = to_update[i]
        new_messages.append(m)
    return new_messages, True


@router.post("/dedup-system-messages")
def dedup_system_messages():
    def generate():
        with get_conn() as conn:
            rows = conn.execute("SELECT id, input FROM records").fetchall()

        total = len(rows)
        yield f"data: {json.dumps({'stage': 'processing', 'progress': 0, 'total': total, 'message': f'共 {total} 条记录'})}\n\n"

        modified_count = 0
        messages_removed = 0
        updates = []

        for i, row in enumerate(rows):
            try:
                inp = json.loads(row["input"]) if row["input"] else {}
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(inp, dict):
                continue
            messages = inp.get("messages", [])
            if not messages:
                continue

            new_messages, changed = _dedup_system_messages(messages)
            if changed:
                removed = len(messages) - len(new_messages)
                messages_removed += removed
                modified_count += 1
                inp["messages"] = new_messages
                updates.append((json.dumps(inp, ensure_ascii=False), row["id"]))

            #if (i + 1) % 50 == 0 or i == total - 1:
            yield f"data: {json.dumps({'stage': 'processing', 'progress': i + 1, 'total': total, 'message': f'扫描中 {i+1}/{total}，已修改 {modified_count}'})}\n\n"

        if not updates:
            yield f"data: {json.dumps({'stage': 'done', 'result': {'modified': 0, 'messages_removed': 0, 'total': total}})}\n\n"
            return

        with get_conn() as conn:
            batch_size = 100
            for start in range(0, len(updates), batch_size):
                batch = updates[start:start + batch_size]
                conn.executemany("UPDATE records SET input = ? WHERE id = ?", batch)
                conn.commit()
                yield f"data: {json.dumps({'stage': 'updating', 'progress': min(start + batch_size, len(updates)), 'total': len(updates), 'message': f'更新中 {min(start + batch_size, len(updates))}/{len(updates)}'})}\n\n"

        yield f"data: {json.dumps({'stage': 'done', 'result': {'modified': modified_count, 'messages_removed': messages_removed, 'total': total}})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


def _merge_consecutive_system(messages):
    if len(messages) < 2:
        return messages, False
    result = []
    changed = False
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.get("role") != "system":
            result.append(msg)
            i += 1
            continue
        texts = [extract_text(msg.get("content"))]
        j = i + 1
        while j < len(messages) and messages[j].get("role") == "system":
            texts.append(extract_text(messages[j].get("content")))
            j += 1
        if j > i + 1:
            merged = dict(msg)
            merged["content"] = "\n".join(t for t in texts if t)
            result.append(merged)
            changed = True
        else:
            result.append(msg)
        i = j
    return result, changed


@router.post("/merge-consecutive-system")
def merge_consecutive_system():
    def generate():
        with get_conn() as conn:
            rows = conn.execute("SELECT id, input FROM records").fetchall()

        total = len(rows)
        yield f"data: {json.dumps({'stage': 'processing', 'progress': 0, 'total': total, 'message': f'共 {total} 条记录'})}\n\n"

        modified_count = 0
        messages_merged = 0
        updates = []

        for i, row in enumerate(rows):
            try:
                inp = json.loads(row["input"]) if row["input"] else {}
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(inp, dict):
                continue
            messages = inp.get("messages", [])
            if not messages:
                continue

            new_messages, changed = _merge_consecutive_system(messages)
            if changed:
                removed = len(messages) - len(new_messages)
                messages_merged += removed
                modified_count += 1
                inp["messages"] = new_messages
                updates.append((json.dumps(inp, ensure_ascii=False), row["id"]))

            yield f"data: {json.dumps({'stage': 'processing', 'progress': i + 1, 'total': total, 'message': f'扫描中 {i+1}/{total}，已修改 {modified_count}'})}\n\n"

        if not updates:
            yield f"data: {json.dumps({'stage': 'done', 'result': {'modified': 0, 'messages_merged': 0, 'total': total}})}\n\n"
            return

        with get_conn() as conn:
            batch_size = 100
            for start in range(0, len(updates), batch_size):
                batch = updates[start:start + batch_size]
                conn.executemany("UPDATE records SET input = ? WHERE id = ?", batch)
                conn.commit()
                yield f"data: {json.dumps({'stage': 'updating', 'progress': min(start + batch_size, len(updates)), 'total': len(updates), 'message': f'更新中 {min(start + batch_size, len(updates))}/{len(updates)}'})}\n\n"

        yield f"data: {json.dumps({'stage': 'done', 'result': {'modified': modified_count, 'messages_merged': messages_merged, 'total': total}})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

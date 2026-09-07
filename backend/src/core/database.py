import sqlite3
import json
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Optional
from src.core.models import EmailMessage, ReplyDraft, ThreadState, LLMTriageOutput
from src.core.crypto import decrypt_text, encrypt_text

DB_PATH = "triage_state.db"


def _with_action_ids(thread_id: str, triage_data: dict) -> dict:
    actions = triage_data.get("required_actions", [])
    deduplicated = []
    normalized_actions = []
    for action in actions:
        normalized = " ".join(action.get("task_description", "").lower().split())
        matching_index = next(
            (
                index for index, candidate in enumerate(normalized_actions)
                if SequenceMatcher(None, normalized, candidate).ratio() >= 0.82
            ),
            None,
        )
        if matching_index is not None:
            current = deduplicated[matching_index]
            current["deadline"] = action.get("deadline") or current.get("deadline")
            current["is_resolved"] = action.get("is_resolved", False) or current.get("is_resolved", False)
            continue

        action = dict(action)
        if not action.get("action_id"):
            action["action_id"] = f"{thread_id}-action-{len(deduplicated) + 1}"
        deduplicated.append(action)
        normalized_actions.append(normalized)
    triage_data["required_actions"] = deduplicated
    return triage_data

def init_db():
    """Initialises the SQLite table for thread persistence."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                thread_id TEXT PRIMARY KEY,
                handler_type TEXT,
                last_updated TEXT,
                message_count INTEGER,
                current_triage JSON,
                internal_notes JSON
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                step TEXT NOT NULL,
                message_id TEXT,
                model TEXT,
                prompt_version TEXT,
                details JSON NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reply_drafts (
                draft_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                draft_type TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                sent_from TEXT NOT NULL,
                sent_to JSON NOT NULL,
                sent_cc JSON NOT NULL,
                date_sent TEXT NOT NULL,
                attachments JSON NOT NULL,
                importance_flag TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_debounce (
                thread_id TEXT PRIMARY KEY,
                due_at TEXT NOT NULL,
                message_ids JSON NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS access_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at TEXT NOT NULL,
                user_id TEXT,
                role TEXT,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                handler_type TEXT,
                client_host TEXT
            )
        """)
        conn.commit()

def get_all_threads() -> list[ThreadState]:
    """Returns all persisted thread states for Q&A context."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM threads ORDER BY last_updated DESC")
        rows = cursor.fetchall()
        results = []
        for row in rows:
            triage_data = _with_action_ids(row["thread_id"], json.loads(decrypt_text(row["current_triage"])))
            results.append(ThreadState(
                thread_id=row["thread_id"],
                handler_type=row["handler_type"],
                last_updated=row["last_updated"],
                message_count=row["message_count"],
                current_triage=LLMTriageOutput(**triage_data),
                internal_notes=json.loads(decrypt_text(row["internal_notes"]))
            ))
        return results


def save_thread_state(state: ThreadState) -> None:
    """Upserts the latest thread evaluation into the database."""
    for index, action in enumerate(state.current_triage.required_actions):
        if not action.action_id:
            action.action_id = f"{state.thread_id}-action-{index + 1}"

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO threads (thread_id, handler_type, last_updated, message_count, current_triage, internal_notes)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                last_updated=excluded.last_updated,
                message_count=excluded.message_count,
                current_triage=excluded.current_triage,
                internal_notes=excluded.internal_notes
        """, (
            state.thread_id,
            state.handler_type,
            state.last_updated.isoformat(),
            state.message_count,
            encrypt_text(json.dumps(_with_action_ids(state.thread_id, state.current_triage.model_dump(mode="json")))),
            encrypt_text(json.dumps(state.internal_notes))
        ))
        conn.commit()

def get_thread_state(thread_id: str) -> Optional[ThreadState]:
    """Retrieves existing thread history for follow-up evaluation."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM threads WHERE thread_id = ?", (thread_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
            
        triage_data = _with_action_ids(row["thread_id"], json.loads(decrypt_text(row["current_triage"])))
        return ThreadState(
            thread_id=row["thread_id"],
            handler_type=row["handler_type"],
            last_updated=row["last_updated"],
            message_count=row["message_count"],
            current_triage=LLMTriageOutput(**triage_data),
            internal_notes=json.loads(decrypt_text(row["internal_notes"]))
        )


def save_messages(messages: list[EmailMessage]) -> None:
    """Persists raw source messages idempotently for later retrieval and audit."""
    if not messages:
        return

    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            """
            INSERT INTO messages (
                message_id, thread_id, subject, body, sent_from, sent_to,
                sent_cc, date_sent, attachments, importance_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO NOTHING
            """,
            [
                (
                    message.message_id,
                    message.thread_id,
                    encrypt_text(message.subject),
                    encrypt_text(message.body),
                    encrypt_text(str(message.sent_from)),
                    json.dumps([str(address) for address in message.sent_to]),
                    json.dumps([str(address) for address in (message.sent_cc or [])]),
                    message.date_sent.isoformat(),
                    json.dumps([attachment.model_dump(mode="json") for attachment in (message.attachments or [])]),
                    message.importance_flag,
                )
                for message in messages
            ],
        )
        conn.commit()


def get_thread_messages(thread_id: str) -> list[EmailMessage]:
    """Returns original messages in chronological order for a thread."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT message_id, thread_id, subject, body, sent_from, sent_to,
                   sent_cc, date_sent, attachments, importance_flag
            FROM messages
            WHERE thread_id = ?
            ORDER BY date_sent ASC
            """,
            (thread_id,),
        ).fetchall()

    return [
        EmailMessage(
            message_id=row["message_id"],
            thread_id=row["thread_id"],
            subject=decrypt_text(row["subject"]),
            body=decrypt_text(row["body"]),
            sent_from=decrypt_text(row["sent_from"]),
            sent_to=json.loads(row["sent_to"]),
            sent_cc=json.loads(row["sent_cc"]),
            date_sent=row["date_sent"],
            attachments=json.loads(row["attachments"]),
            importance_flag=row["importance_flag"],
        )
        for row in rows
    ]


def save_pending_debounce(thread_id: str, due_at: datetime, messages: list[EmailMessage]) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO pending_debounce (thread_id, due_at, message_ids)
            VALUES (?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                due_at=excluded.due_at,
                message_ids=excluded.message_ids
            """,
            (thread_id, due_at.isoformat(), json.dumps([message.message_id for message in messages])),
        )
        conn.commit()


def delete_pending_debounce(thread_id: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM pending_debounce WHERE thread_id = ?", (thread_id,))
        conn.commit()


def get_pending_debounces() -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT thread_id, due_at, message_ids FROM pending_debounce"
        ).fetchall()
    return [
        {
            "thread_id": row["thread_id"],
            "due_at": datetime.fromisoformat(row["due_at"]),
            "message_ids": json.loads(row["message_ids"]),
        }
        for row in rows
    ]


def get_messages_by_ids(message_ids: list[str]) -> list[EmailMessage]:
    if not message_ids:
        return []
    placeholders = ",".join("?" for _ in message_ids)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM messages WHERE message_id IN ({placeholders})",
            message_ids,
        ).fetchall()
    messages = {
        row["message_id"]: EmailMessage(
            message_id=row["message_id"],
            thread_id=row["thread_id"],
            subject=decrypt_text(row["subject"]),
            body=decrypt_text(row["body"]),
            sent_from=decrypt_text(row["sent_from"]),
            sent_to=json.loads(row["sent_to"]),
            sent_cc=json.loads(row["sent_cc"]),
            date_sent=row["date_sent"],
            attachments=json.loads(row["attachments"]),
            importance_flag=row["importance_flag"],
        )
        for row in rows
    }
    return [messages[message_id] for message_id in message_ids if message_id in messages]


def delete_thread_data(thread_id: str) -> bool:
    """Deletes all locally retained data associated with a thread."""
    with sqlite3.connect(DB_PATH) as conn:
        exists = conn.execute("SELECT 1 FROM threads WHERE thread_id = ?", (thread_id,)).fetchone()
        if not exists:
            return False
        for table in ("threads", "messages", "audit_events", "reply_drafts", "pending_debounce"):
            conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (thread_id,))
        conn.commit()
    return True


def purge_threads_older_than(cutoff: datetime) -> int:
    """Deletes complete thread records older than the supplied UTC cutoff."""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT thread_id FROM threads WHERE last_updated < ?",
            (cutoff.isoformat(),),
        ).fetchall()
        thread_ids = [row[0] for row in rows]
        for thread_id in thread_ids:
            for table in ("threads", "messages", "audit_events", "reply_drafts", "pending_debounce"):
                conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (thread_id,))
        conn.commit()
    return len(thread_ids)


def save_access_event(event: dict[str, Any]) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO access_events (
                occurred_at, user_id, role, method, path, status_code,
                handler_type, client_host
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["occurred_at"], event.get("user_id"), event.get("role"),
                event["method"], event["path"], event["status_code"],
                event.get("handler_type"), event.get("client_host"),
            ),
        )
        conn.commit()


def get_access_events(limit: int = 200) -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT event_id, occurred_at, user_id, role, method, path,
                   status_code, handler_type, client_host
            FROM access_events ORDER BY event_id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def save_audit_events(thread_id: str, events: list[dict[str, Any]]) -> None:
    """Persists non-content processing events for a triage run."""
    if not events:
        return

    occurred_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            """
            INSERT INTO audit_events (
                thread_id, occurred_at, step, message_id, model, prompt_version, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    thread_id,
                    event.get("occurred_at", occurred_at),
                    event.get("step", "unknown"),
                    event.get("message_id"),
                    event.get("model"),
                    event.get("prompt_version"),
                    encrypt_text(json.dumps(event.get("details", {}))),
                )
                for event in events
            ],
        )
        conn.commit()


def get_audit_events(thread_id: str) -> list[dict[str, Any]]:
    """Returns the persisted processing history for a thread."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT event_id, thread_id, occurred_at, step, message_id,
                   model, prompt_version, details
            FROM audit_events
            WHERE thread_id = ?
            ORDER BY event_id ASC
            """,
            (thread_id,),
        ).fetchall()

    return [
        {
            "event_id": row["event_id"],
            "thread_id": row["thread_id"],
            "occurred_at": row["occurred_at"],
            "step": row["step"],
            "message_id": row["message_id"],
            "model": row["model"],
            "prompt_version": row["prompt_version"],
            "details": json.loads(decrypt_text(row["details"])),
        }
        for row in rows
    ]


def save_reply_draft(draft: ReplyDraft) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO reply_drafts (
                draft_id, thread_id, draft_type, body, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(draft_id) DO UPDATE SET
                body=excluded.body,
                status=excluded.status,
                updated_at=excluded.updated_at
            """,
            (
                draft.draft_id,
                draft.thread_id,
                draft.draft_type,
                encrypt_text(draft.body),
                draft.status,
                draft.created_at.isoformat(),
                draft.updated_at.isoformat(),
            ),
        )
        conn.commit()


def get_reply_draft(draft_id: str) -> Optional[ReplyDraft]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM reply_drafts WHERE draft_id = ?", (draft_id,)
        ).fetchone()

    if not row:
        return None
    return ReplyDraft(
        draft_id=row["draft_id"],
        thread_id=row["thread_id"],
        draft_type=row["draft_type"],
        body=decrypt_text(row["body"]),
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_thread_drafts(thread_id: str) -> list[ReplyDraft]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM reply_drafts WHERE thread_id = ? ORDER BY created_at DESC",
            (thread_id,),
        ).fetchall()
    return [
        ReplyDraft(
            draft_id=row["draft_id"],
            thread_id=row["thread_id"],
            draft_type=row["draft_type"],
            body=decrypt_text(row["body"]),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]
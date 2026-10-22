"""MVP authentication, presence, invitation, and activity APIs.

This module intentionally uses the repository's existing sqlite3 approach. It is
prototype infrastructure: account passwords are stored as supplied in SQLite
and must be replaced with password hashing before production use.
"""
import json
import os
import secrets
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel, Field
from storage import connect, USE_POSTGRES

SESSION_COOKIE = os.getenv("CAREMATRIX_SESSION_COOKIE", "carematrix_session")
EXPIRY_SECONDS = int(os.getenv("CAREMATRIX_PRESENCE_EXPIRY_SECONDS", "30"))

router = APIRouter()


def db():
    return connect()


def migrate():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS hospital_accounts (
      id TEXT PRIMARY KEY, hospital_id TEXT NOT NULL, username TEXT UNIQUE NOT NULL,
      password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'admin', active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS hospital_sessions (
      id TEXT PRIMARY KEY, account_id TEXT NOT NULL, hospital_id TEXT NOT NULL,
      created_at INTEGER NOT NULL, last_seen INTEGER NOT NULL, signed_out INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS transfer_invitations (
      id TEXT PRIMARY KEY, transfer_id TEXT NOT NULL, recipient_hospital_id TEXT NOT NULL,
      response TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL, responded_at INTEGER,
      UNIQUE(transfer_id, recipient_hospital_id)
    );
    CREATE TABLE IF NOT EXISTS resource_invitations (
      id TEXT PRIMARY KEY, request_id TEXT NOT NULL, recipient_hospital_id TEXT NOT NULL,
      response TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL, responded_at INTEGER,
      UNIQUE(request_id, recipient_hospital_id)
    );
    CREATE TABLE IF NOT EXISTS audit_events (
      id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
      event_type TEXT NOT NULL, actor_hospital_id TEXT, actor_account_id TEXT,
      created_at INTEGER NOT NULL, metadata TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_sessions_presence ON hospital_sessions(hospital_id, last_seen, signed_out);
    CREATE INDEX IF NOT EXISTS idx_transfer_invites ON transfer_invitations(transfer_id, recipient_hospital_id);
    CREATE INDEX IF NOT EXISTS idx_resource_invites ON resource_invitations(request_id, recipient_hospital_id);
    """)
    for table, additions in {
        "hospitals": [("location", "TEXT"), ("logo_url", "TEXT"), ("created_at", "INTEGER")],
        "patients": [("requester_hospital_id", "TEXT"), ("created_at", "INTEGER"), ("updated_at", "INTEGER")],
        "resource_requests": [("requester_hospital_id", "TEXT"), ("selected_provider_id", "TEXT"), ("created_at", "INTEGER"), ("updated_at", "INTEGER")],
    }.items():
        table_exists_sql = "SELECT 1 FROM information_schema.tables WHERE table_schema=current_schema() AND table_name=?" if USE_POSTGRES else "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?"
        if not conn.execute(table_exists_sql, (table,)).fetchone():
            continue
        if USE_POSTGRES:
            existing = {row[0] for row in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=?", (table,)).fetchall()}
        else:
            existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, kind in additions:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
    conn.commit()
    conn.close()


migrate()


def now():
    return int(time.time())


def session_hospital(session_id: Optional[str]):
    if not session_id:
        raise HTTPException(401, "Authentication required")
    conn = db()
    row = conn.execute("""SELECT s.*, a.username, a.role, h.name, h.location, h.lat, h.lng, h.logo_url
        FROM hospital_sessions s JOIN hospital_accounts a ON a.id=s.account_id
        JOIN hospitals h ON h.id=s.hospital_id
        WHERE s.id=? AND s.signed_out=0 AND a.active=1""", (session_id,)).fetchone()
    if not row or now() - row["last_seen"] > EXPIRY_SECONDS:
        conn.close()
        raise HTTPException(401, "Session expired")
    conn.close()
    return row


class LoginData(BaseModel):
    username: str
    password: str


class ResponseData(BaseModel):
    response: str = Field(pattern="^(accepted|rejected)$")


class SelectData(BaseModel):
    hospital_id: str


def audit(conn, entity_type, entity_id, event_type, actor=None, metadata=None):
    conn.execute("INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (str(uuid.uuid4()), entity_type, entity_id, event_type,
                  actor["hospital_id"] if actor else None, actor["account_id"] if actor else None,
                  now(), json.dumps(metadata or {})))


@router.post("/api/auth/login")
def login(data: LoginData, response: Response):
    conn = db()
    account = conn.execute("SELECT * FROM hospital_accounts WHERE username=? AND password=? AND active=1",
                           (data.username.strip(), data.password)).fetchone()
    if not account:
        conn.close()
        raise HTTPException(401, "Invalid credentials")
    hospital = conn.execute("SELECT * FROM hospitals WHERE id=?", (account["hospital_id"],)).fetchone()
    if not hospital:
        conn.close()
        raise HTTPException(409, "Account is not linked to a hospital")
    sid = secrets.token_urlsafe(32)
    t = now()
    conn.execute("INSERT INTO hospital_sessions VALUES (?, ?, ?, ?, ?, 0)",
                 (sid, account["id"], account["hospital_id"], t, t))
    conn.commit(); conn.close()
    response.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="lax", max_age=86400)
    return {"hospital": dict(hospital), "username": account["username"], "role": account["role"]}


@router.get("/api/auth/me")
def me(carematrix_session: Optional[str] = Cookie(default=None)):
    row = session_hospital(carematrix_session)
    return {"hospital": {k: row[k] for k in ("hospital_id", "name", "location", "lat", "lng", "logo_url")},
            "username": row["username"], "role": row["role"]}


@router.post("/api/auth/heartbeat")
def heartbeat(carematrix_session: Optional[str] = Cookie(default=None)):
    row = session_hospital(carematrix_session)
    conn = db(); conn.execute("UPDATE hospital_sessions SET last_seen=? WHERE id=?", (now(), row["id"])); conn.commit(); conn.close()
    return {"status": "active", "hospital_id": row["hospital_id"]}


@router.post("/api/auth/logout")
def logout(response: Response, carematrix_session: Optional[str] = Cookie(default=None)):
    if carematrix_session:
        conn = db(); conn.execute("UPDATE hospital_sessions SET signed_out=1 WHERE id=?", (carematrix_session,)); conn.commit(); conn.close()
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "signed_out"}


@router.get("/api/hospitals/active")
def active_hospitals():
    cutoff = now() - EXPIRY_SECONDS
    conn = db()
    rows = conn.execute("""SELECT h.id, h.name, h.location, h.lat, h.lng, h.logo_url,
        CASE WHEN EXISTS (SELECT 1 FROM hospital_sessions s WHERE s.hospital_id=h.id AND s.signed_out=0 AND s.last_seen>=?) THEN 1 ELSE 0 END active
        FROM hospitals h ORDER BY h.name""", (cutoff,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@router.get("/api/hospitals/active/count")
def active_count():
    return {"count": sum(1 for h in active_hospitals() if h["active"])}


@router.get("/api/transfer/incoming")
def incoming_transfers(carematrix_session: Optional[str] = Cookie(default=None)):
    actor = session_hospital(carematrix_session); conn = db()
    rows = conn.execute("""SELECT p.id, p.department, p.priority, p.lat, p.lng, p.status, p.created_at,
        h.id requester_id, h.name requester_name, h.location requester_location, h.logo_url requester_logo,
        i.response
        FROM transfer_invitations i JOIN patients p ON p.id=i.transfer_id JOIN hospitals h ON h.id=p.requester_hospital_id
        WHERE i.recipient_hospital_id=? AND p.status IN ('open','broadcast') ORDER BY p.created_at DESC""", (actor["hospital_id"],)).fetchall()
    conn.close(); return [dict(r) for r in rows]


@router.get("/api/transfer/outgoing")
def outgoing_transfers(carematrix_session: Optional[str] = Cookie(default=None)):
    actor = session_hospital(carematrix_session); conn = db()
    rows = conn.execute("""SELECT p.id, p.department, p.priority, p.status, p.created_at,
        COUNT(i.id) notified, SUM(CASE WHEN i.response!='pending' THEN 1 ELSE 0 END) responded,
        SUM(CASE WHEN i.response='accepted' THEN 1 ELSE 0 END) accepted,
        SUM(CASE WHEN i.response='rejected' THEN 1 ELSE 0 END) rejected
        FROM patients p LEFT JOIN transfer_invitations i ON i.transfer_id=p.id
        WHERE p.requester_hospital_id=? GROUP BY p.id ORDER BY p.created_at DESC""", (actor["hospital_id"],)).fetchall()
    conn.close(); return [dict(r) for r in rows]


@router.post("/api/transfer/{transfer_id}/respond")
def transfer_response(transfer_id: str, data: ResponseData, carematrix_session: Optional[str] = Cookie(default=None)):
    actor = session_hospital(carematrix_session); conn = db()
    inv = conn.execute("SELECT * FROM transfer_invitations WHERE transfer_id=? AND recipient_hospital_id=?", (transfer_id, actor["hospital_id"])).fetchone()
    req = conn.execute("SELECT * FROM patients WHERE id=?", (transfer_id,)).fetchone()
    if not inv or not req: conn.close(); raise HTTPException(404, "Invitation not found")
    if req["status"] not in ("open", "broadcast"): conn.close(); raise HTTPException(409, "Request is no longer open")
    conn.execute("UPDATE transfer_invitations SET response=?, responded_at=? WHERE id=?", (data.response, now(), inv["id"]))
    audit(conn, "transfer", transfer_id, data.response, actor)
    conn.commit(); conn.close(); return {"status": data.response}


@router.get("/api/transfer/{transfer_id}/timeline")
def transfer_timeline(transfer_id: str, carematrix_session: Optional[str] = Cookie(default=None)):
    actor = session_hospital(carematrix_session); conn = db()
    req = conn.execute("SELECT requester_hospital_id FROM patients WHERE id=?", (transfer_id,)).fetchone()
    if not req or req["requester_hospital_id"] != actor["hospital_id"] and not conn.execute("SELECT 1 FROM transfer_invitations WHERE transfer_id=? AND recipient_hospital_id=?", (transfer_id, actor["hospital_id"])).fetchone():
        conn.close(); raise HTTPException(404, "Transfer not found")
    rows = conn.execute("SELECT * FROM audit_events WHERE entity_type='transfer' AND entity_id=? ORDER BY created_at", (transfer_id,)).fetchall(); conn.close(); return [dict(r) for r in rows]


@router.get("/api/resource/incoming")
def incoming_resources(carematrix_session: Optional[str] = Cookie(default=None)):
    actor = session_hospital(carematrix_session); conn = db()
    rows = conn.execute("""SELECT r.id, r.resource_type, r.quantity, r.status, r.created_at,
        h.id requester_id, h.name requester_name, h.logo_url requester_logo, i.response
        FROM resource_invitations i JOIN resource_requests r ON r.id=i.request_id
        JOIN hospitals h ON h.id=r.requester_hospital_id
        WHERE i.recipient_hospital_id=? AND r.status='open' ORDER BY r.created_at DESC""", (actor["hospital_id"],)).fetchall()
    conn.close(); return [dict(r) for r in rows]


@router.get("/api/resource/outgoing")
def outgoing_resources(carematrix_session: Optional[str] = Cookie(default=None)):
    actor = session_hospital(carematrix_session); conn = db()
    rows = conn.execute("""SELECT r.id, r.resource_type, r.quantity, r.status, r.created_at,
        COUNT(i.id) notified, SUM(CASE WHEN i.response!='pending' THEN 1 ELSE 0 END) responded,
        SUM(CASE WHEN i.response='accepted' THEN 1 ELSE 0 END) accepted,
        SUM(CASE WHEN i.response='rejected' THEN 1 ELSE 0 END) rejected
        FROM resource_requests r LEFT JOIN resource_invitations i ON i.request_id=r.id
        WHERE r.requester_hospital_id=? GROUP BY r.id ORDER BY r.created_at DESC""", (actor["hospital_id"],)).fetchall()
    conn.close(); return [dict(r) for r in rows]


@router.post("/api/resource/{request_id}/respond")
def resource_response(request_id: str, data: ResponseData, carematrix_session: Optional[str] = Cookie(default=None)):
    actor = session_hospital(carematrix_session); conn = db()
    inv = conn.execute("SELECT * FROM resource_invitations WHERE request_id=? AND recipient_hospital_id=?", (request_id, actor["hospital_id"])).fetchone()
    if not inv: conn.close(); raise HTTPException(404, "Invitation not found")
    conn.execute("UPDATE resource_invitations SET response=?, responded_at=? WHERE id=?", (data.response, now(), inv["id"]))
    audit(conn, "resource", request_id, data.response, actor); conn.commit(); conn.close(); return {"status": data.response}


@router.post("/api/resource/{request_id}/select")
def select_resource(request_id: str, data: SelectData, carematrix_session: Optional[str] = Cookie(default=None)):
    actor = session_hospital(carematrix_session); conn = db()
    request = conn.execute("SELECT * FROM resource_requests WHERE id=? AND requester_hospital_id=?", (request_id, actor["hospital_id"])).fetchone()
    offer = conn.execute("SELECT 1 FROM resource_invitations WHERE request_id=? AND recipient_hospital_id=? AND response='accepted'", (request_id, data.hospital_id)).fetchone()
    if not request or not offer or request["status"] != "open": conn.close(); raise HTTPException(409, "Provider is not selectable")
    conn.execute("UPDATE resource_requests SET status='fulfilled', selected_provider_id=?, updated_at=? WHERE id=? AND status='open'", (data.hospital_id, now(), request_id))
    conn.execute("UPDATE resource_invitations SET response='closed' WHERE request_id=? AND response='pending'", (request_id, request_id))
    audit(conn, "resource", request_id, "provider_selected", actor, {"provider_id": data.hospital_id}); conn.commit(); conn.close(); return {"status": "fulfilled", "provider_id": data.hospital_id}

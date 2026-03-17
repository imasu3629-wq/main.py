import sqlite3

import os
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        # UUIDキャッシュ（Mojang API節約）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS uuid_cache (
                mcid TEXT PRIMARY KEY,
                uuid TEXT NOT NULL,
                cached_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # ユーザー登録テーブル（UUID主キー）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS registrations (
                uuid TEXT PRIMARY KEY,
                mcid TEXT NOT NULL,
                discord_id TEXT NOT NULL,
                star INTEGER DEFAULT 0,
                fkdr REAL DEFAULT 0.0,
                registered_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

# --- UUID キャッシュ ---
def get_cached_uuid(mcid: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT uuid FROM uuid_cache WHERE mcid = ? AND cached_at > datetime('now', '-1 days')",
            (mcid.lower(),)
        ).fetchone()
        return row["uuid"] if row else None

def save_uuid_cache(mcid: str, uuid: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO uuid_cache (mcid, uuid, cached_at) VALUES (?, ?, datetime('now'))",
            (mcid.lower(), uuid)
        )

# --- 登録 ---
def register_player(uuid: str, mcid: str, discord_id: str, star: int, fkdr: float):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO registrations (uuid, mcid, discord_id, star, fkdr, registered_at, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (uuid, mcid, str(discord_id), star, fkdr))

def update_stats(uuid: str, mcid: str, star: int, fkdr: float):
    with get_conn() as conn:
        conn.execute("""
            UPDATE registrations
            SET star = ?, fkdr = ?, mcid = ?, updated_at = datetime('now')
            WHERE uuid = ?
        """, (star, fkdr, mcid, uuid))

def is_registered(uuid: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM registrations WHERE uuid = ?", (uuid,)).fetchone()
        return row is not None

def is_registered_by_discord(discord_id: str, uuid: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM registrations WHERE discord_id = ? AND uuid = ?",
            (str(discord_id), uuid)
        ).fetchone()
        return row is not None

# --- 一覧 ---
def get_registered_by_discord(discord_id: str):
    with get_conn() as conn:
        return conn.execute("""
            SELECT mcid, star, fkdr, updated_at
            FROM registrations
            WHERE discord_id = ?
            ORDER BY fkdr DESC
        """, (str(discord_id),)).fetchall()

# --- ランキング ---
def get_ranking_by_fkdr(limit=10):
    with get_conn() as conn:
        return conn.execute("""
            SELECT mcid, star, fkdr, updated_at
            FROM registrations
            ORDER BY fkdr DESC
            LIMIT ?
        """, (limit,)).fetchall()

def get_ranking_by_star(limit=10):
    with get_conn() as conn:
        return conn.execute("""
            SELECT mcid, star, fkdr, updated_at
            FROM registrations
            ORDER BY star DESC
            LIMIT ?
        """, (limit,)).fetchall()

# --- 削除 ---
def delete_player(discord_id: str, uuid: str) -> bool:
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM registrations WHERE discord_id = ? AND uuid = ?",
            (str(discord_id), uuid)
        )
        return cursor.rowcount > 0

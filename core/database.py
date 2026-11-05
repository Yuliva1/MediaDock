
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from config.paths import DB_PATH


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DatabaseManager:

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
            self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS media_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                source_url TEXT DEFAULT '',
                platform TEXT DEFAULT 'Web Medya',
                uploader TEXT DEFAULT '',
                duration REAL DEFAULT 0,
                resolution TEXT DEFAULT '',
                format TEXT DEFAULT '',
                video_codec TEXT DEFAULT '',
                audio_codec TEXT DEFAULT '',
                file_size INTEGER DEFAULT 0,
                thumbnail_path TEXT DEFAULT '',
                premiere_ready INTEGER DEFAULT 0,
                is_favorite INTEGER DEFAULT 0,
                downloaded_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_media_downloaded_at ON media_items(downloaded_at DESC);
            CREATE INDEX IF NOT EXISTS idx_media_favorite ON media_items(is_favorite);
            CREATE INDEX IF NOT EXISTS idx_media_platform ON media_items(platform);

            CREATE TABLE IF NOT EXISTS download_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT DEFAULT '',
                title TEXT NOT NULL,
                source_url TEXT NOT NULL,
                platform TEXT DEFAULT 'Web Medya',
                uploader TEXT DEFAULT '',
                format TEXT DEFAULT '',
                quality TEXT DEFAULT '',
                file_path TEXT DEFAULT '',
                file_size INTEGER DEFAULT 0,
                duration REAL DEFAULT 0,
                thumbnail_path TEXT DEFAULT '',
                premiere_optimized INTEGER DEFAULT 0,
                status TEXT DEFAULT 'completed',
                downloaded_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_history_downloaded_at ON download_history(downloaded_at DESC);

            CREATE TABLE IF NOT EXISTS download_tasks (
                task_id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                platform TEXT DEFAULT 'Web Medya',
                uploader TEXT DEFAULT '',
                duration REAL DEFAULT 0,
                thumbnail_path TEXT DEFAULT '',
                thumbnail_url TEXT DEFAULT '',
                video_format TEXT DEFAULT 'MP4',
                quality_label TEXT DEFAULT 'En iyi kalite',
                target_height INTEGER,
                audio_mode TEXT DEFAULT 'video',
                premiere_optimize INTEGER DEFAULT 0,
                output_dir TEXT NOT NULL,
                file_stem TEXT NOT NULL,
                final_path TEXT DEFAULT '',
                status TEXT NOT NULL,
                progress REAL DEFAULT 0.0,
                downloaded_bytes INTEGER DEFAULT 0,
                total_bytes INTEGER DEFAULT 0,
                error_message TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def get_all_settings(self) -> dict[str, str]:
        with self._lock:
            cur = self._conn.execute("SELECT key, value FROM app_settings")
            return {row["key"]: row["value"] for row in cur.fetchall()}

    def set_settings_bulk(self, values: dict[str, str]) -> None:
        with self._lock:
            self._conn.executemany(
                "INSERT INTO app_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                list(values.items()),
            )
            self._conn.commit()

    def upsert_media_item(
        self,
        *,
        title: str,
        file_name: str,
        file_path: str,
        source_url: str = "",
        platform: str = "Web Medya",
        uploader: str = "",
        duration: float = 0.0,
        resolution: str = "",
        format_name: str = "",
        video_codec: str = "",
        audio_codec: str = "",
        file_size: int = 0,
        thumbnail_path: str = "",
        premiere_ready: bool = False,
        downloaded_at: str | None = None,
    ) -> int:
        ts = downloaded_at or now_iso()
        normalized_path = str(Path(file_path).resolve())
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO media_items (
                    title, file_name, file_path, source_url, platform, uploader,
                    duration, resolution, format, video_codec, audio_codec,
                    file_size, thumbnail_path, premiere_ready, downloaded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    title = excluded.title,
                    file_name = excluded.file_name,
                    source_url = CASE WHEN excluded.source_url != '' THEN excluded.source_url ELSE media_items.source_url END,
                    platform = CASE WHEN excluded.platform != 'Web Medya' THEN excluded.platform ELSE media_items.platform END,
                    uploader = CASE WHEN excluded.uploader != '' THEN excluded.uploader ELSE media_items.uploader END,
                    duration = CASE WHEN excluded.duration > 0 THEN excluded.duration ELSE media_items.duration END,
                    resolution = CASE WHEN excluded.resolution != '' THEN excluded.resolution ELSE media_items.resolution END,
                    format = excluded.format,
                    video_codec = CASE WHEN excluded.video_codec != '' THEN excluded.video_codec ELSE media_items.video_codec END,
                    audio_codec = CASE WHEN excluded.audio_codec != '' THEN excluded.audio_codec ELSE media_items.audio_codec END,
                    file_size = excluded.file_size,
                    thumbnail_path = CASE WHEN excluded.thumbnail_path != '' THEN excluded.thumbnail_path ELSE media_items.thumbnail_path END,
                    premiere_ready = MAX(media_items.premiere_ready, excluded.premiere_ready)
                """,
                (
                    title,
                    file_name,
                    normalized_path,
                    source_url,
                    platform,
                    uploader,
                    float(duration or 0.0),
                    resolution,
                    format_name,
                    video_codec,
                    audio_codec,
                    int(file_size or 0),
                    thumbnail_path,
                    1 if premiere_ready else 0,
                    ts,
                ),
            )
            self._conn.commit()
            if cur.lastrowid:
                return int(cur.lastrowid)
            row = self._conn.execute(
                "SELECT id FROM media_items WHERE file_path = ?",
                (normalized_path,),
            ).fetchone()
            return int(row["id"]) if row else 0

    def get_media_items(
        self,
        *,
        search: str = "",
        platform: str = "",
        favorites_only: bool = False,
        sort_by: str = "date_desc",
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []

        if favorites_only:
            clauses.append("is_favorite = 1")

        if platform and platform != "Tüm Platformlar":
            clauses.append("platform = ?")
            params.append(platform)

        if search.strip():
            q = f"%{search.strip()}%"
            clauses.append("(title LIKE ? OR file_name LIKE ? OR uploader LIKE ? OR platform LIKE ?)")
            params.extend([q, q, q, q])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        sort_map = {
            "date_desc": "downloaded_at DESC, id DESC",
            "date_asc": "downloaded_at ASC, id ASC",
            "name_asc": " title COLLATE NOCASE ASC",
            "name_desc": "title COLLATE NOCASE DESC",
            "size_desc": "file_size DESC",
            "size_asc": "file_size ASC",
        }
        order_sql = sort_map.get(sort_by, "downloaded_at DESC, id DESC")

        with self._lock:
            cur = self._conn.execute(
                f"SELECT * FROM media_items {where_sql} ORDER BY {order_sql}",
                params,
            )
            return [dict(row) for row in cur.fetchall()]

    def get_media_by_id(self, media_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM media_items WHERE id = ?", (media_id,)).fetchone()
            return dict(row) if row else None

    def get_distinct_platforms(self) -> list[str]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT DISTINCT platform FROM media_items WHERE platform != '' ORDER BY platform COLLATE NOCASE ASC"
            )
            return [row["platform"] for row in cur.fetchall()]

    def get_known_file_paths(self) -> set[str]:
        with self._lock:
            cur = self._conn.execute("SELECT file_path FROM media_items")
            return {str(Path(row["file_path"]).resolve()) for row in cur.fetchall()}

    def toggle_favorite(self, media_id: int) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT is_favorite FROM media_items WHERE id = ?",
                (media_id,),
            ).fetchone()
            if not row:
                return False
            new_val = 0 if int(row["is_favorite"]) else 1
            self._conn.execute(
                "UPDATE media_items SET is_favorite = ? WHERE id = ?",
                (new_val, media_id),
            )
            self._conn.commit()
            return bool(new_val)

    def delete_media_item(self, media_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM media_items WHERE id = ?", (media_id,))
            self._conn.commit()

    def get_media_counts(self) -> tuple[int, int]:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) AS c FROM media_items").fetchone()["c"]
            favs = self._conn.execute("SELECT COUNT(*) AS c FROM media_items WHERE is_favorite = 1").fetchone()["c"]
            return int(total), int(favs)

    def add_history_entry(
        self,
        *,
        task_id: str = "",
        title: str,
        source_url: str,
        platform: str = "Web Medya",
        uploader: str = "",
        format_name: str = "",
        quality: str = "",
        file_path: str = "",
        file_size: int = 0,
        duration: float = 0.0,
        thumbnail_path: str = "",
        premiere_optimized: bool = False,
        status: str = "completed",
    ) -> int:
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO download_history (
                    task_id, title, source_url, platform, uploader, format, quality,
                    file_path, file_size, duration, thumbnail_path,
                    premiere_optimized, status, downloaded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    title,
                    source_url,
                    platform,
                    uploader,
                    format_name,
                    quality,
                    file_path,
                    int(file_size or 0),
                    float(duration or 0.0),
                    thumbnail_path,
                    1 if premiere_optimized else 0,
                    status,
                    now_iso(),
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid or 0)

    def get_history_entries(self, search: str = "") -> list[dict[str, Any]]:
        with self._lock:
            if search.strip():
                q = f"%{search.strip()}%"
                cur = self._conn.execute(
                    """
                    SELECT * FROM download_history
                    WHERE title LIKE ? OR source_url LIKE ? OR platform LIKE ? OR uploader LIKE ?
                    ORDER BY downloaded_at DESC, id DESC
                    """,
                    (q, q, q, q),
                )
            else:
                cur = self._conn.execute("SELECT * FROM download_history ORDER BY downloaded_at DESC, id DESC")
            return [dict(row) for row in cur.fetchall()]

    def delete_history_entry(self, history_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM download_history WHERE id = ?", (history_id,))
            self._conn.commit()

    def clear_history(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM download_history")
            self._conn.commit()

    def save_download_task(self, task: dict[str, Any]) -> None:
        now = now_iso()
        created = task.get("created_at") or now
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO download_tasks (
                    task_id, url, title, platform, uploader, duration,
                    thumbnail_path, thumbnail_url, video_format, quality_label,
                    target_height, audio_mode, premiere_optimize, output_dir,
                    file_stem, final_path, status, progress, downloaded_bytes,
                    total_bytes, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    title = excluded.title,
                    platform = excluded.platform,
                    uploader = excluded.uploader,
                    duration = excluded.duration,
                    thumbnail_path = excluded.thumbnail_path,
                    thumbnail_url = excluded.thumbnail_url,
                    final_path = excluded.final_path,
                    status = excluded.status,
                    progress = excluded.progress,
                    downloaded_bytes = excluded.downloaded_bytes,
                    total_bytes = excluded.total_bytes,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at
                """,
                (
                    task["task_id"],
                    task["url"],
                    task.get("title", "Video"),
                    task.get("platform", "Web Medya"),
                    task.get("uploader", ""),
                    float(task.get("duration") or 0.0),
                    task.get("thumbnail_path", ""),
                    task.get("thumbnail_url", ""),
                    task.get("video_format", "MP4"),
                    task.get("quality_label", "En iyi kalite"),
                    task.get("target_height"),
                    task.get("audio_mode", "video"),
                    1 if task.get("premiere_optimize") else 0,
                    task["output_dir"],
                    task["file_stem"],
                    task.get("final_path", ""),
                    task["status"],
                    float(task.get("progress") or 0.0),
                    int(task.get("downloaded_bytes") or 0),
                    int(task.get("total_bytes") or 0),
                    task.get("error_message", ""),
                    created,
                    now,
                ),
            )
            self._conn.commit()

    def get_recoverable_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT * FROM download_tasks
                WHERE status IN ('queued', 'downloading', 'converting', 'paused', 'failed')
                ORDER BY created_at ASC
                """
            )
            return [dict(row) for row in cur.fetchall()]

    def remove_download_task(self, task_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM download_tasks WHERE task_id = ?", (task_id,))
            self._conn.commit()

    def clear_finished_tasks(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM download_tasks WHERE status IN ('completed', 'cancelled')")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

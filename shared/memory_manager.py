"""
Cognitive Memory Manager for TARS Distributed Dual-Brain Robot.

Provides:
- High-speed local SQLite database (`tars_memory.db`) with WAL mode (`PRAGMA journal_mode = WAL; PRAGMA synchronous = NORMAL;`).
- Zero-latency in-memory RAM cache for 0ms reads and instant startup Boot Recall.
- Auto-migration from existing `tars_memory.json` into SQLite tables without data loss.
- Thread-safe declarative fact storage (`save_fact`) and visual diary logging (`log_visual_diary_entry`).
- Spatial landmark memory schema and logging (`log_landmark_sighting`, `record_landmark`).
- 6-axis personality trait matrix storage (`update_personality`, `get_personality`).
- Timestamped spatial recall (`query_landmark_locations`).
- Multi-criteria memory querying (`query_memory`).
- Startup Boot Recall system instruction generator (`get_boot_recall_context`).
- Unsynced records tracker (`get_unsynced_records`, `mark_records_synced`) for asynchronous Cloudflare D1 synchronization.
- Atomic configuration updater (`save_config_atomic`).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Union
import uuid

logger = logging.getLogger("TARS.Shared.MemoryManager")

DEFAULT_MEMORY_DB_FILENAME = "tars_memory.db"
DEFAULT_MEMORY_JSON_FILENAME = "tars_memory.json"
DEFAULT_CONFIG_FILENAME = "config.json"


def find_memory_path(explicit_path: str | Path | None = None) -> Path:
    """Resolve tars_memory path (preferring .db, fallback to .json or repo root)."""
    if explicit_path:
        return Path(explicit_path).resolve()

    if os.environ.get("TARS_MEMORY_PATH"):
        return Path(os.environ["TARS_MEMORY_PATH"]).resolve()

    # Look for tars_memory.db first
    db_candidates = [
        Path(DEFAULT_MEMORY_DB_FILENAME),
        Path(__file__).resolve().parent.parent / DEFAULT_MEMORY_DB_FILENAME,
        Path("/home/Mishal/robot/TARS") / DEFAULT_MEMORY_DB_FILENAME,
    ]
    for p in db_candidates:
        if p.is_file():
            return p.resolve()

    # Look for tars_memory.json next
    json_candidates = [
        Path(DEFAULT_MEMORY_JSON_FILENAME),
        Path(__file__).resolve().parent.parent / DEFAULT_MEMORY_JSON_FILENAME,
        Path("/home/Mishal/robot/TARS") / DEFAULT_MEMORY_JSON_FILENAME,
    ]
    for p in json_candidates:
        if p.is_file():
            return p.resolve()

    # Default to repo root if available, otherwise current working directory
    repo_candidate = Path(__file__).resolve().parent.parent / DEFAULT_MEMORY_DB_FILENAME
    if repo_candidate.parent.exists():
        return repo_candidate.resolve()
    return Path(DEFAULT_MEMORY_DB_FILENAME).resolve()


def find_config_path(explicit_path: str | Path | None = None) -> Path:
    """Resolve config.json path with fallback search."""
    if explicit_path:
        return Path(explicit_path).resolve()

    if os.environ.get("TARS_CONFIG"):
        return Path(os.environ["TARS_CONFIG"]).resolve()

    candidates = [
        Path(DEFAULT_CONFIG_FILENAME),
        Path(__file__).resolve().parent.parent / DEFAULT_CONFIG_FILENAME,
        Path("/home/Mishal/robot/TARS") / DEFAULT_CONFIG_FILENAME,
    ]

    for p in candidates:
        if p.is_file():
            return p.resolve()

    repo_candidate = Path(__file__).resolve().parent.parent / DEFAULT_CONFIG_FILENAME
    if repo_candidate.parent.exists():
        return repo_candidate.resolve()
    return Path(DEFAULT_CONFIG_FILENAME).resolve()


def atomic_write_json(file_path: str | Path, data: dict[str, Any]) -> None:
    """
    Atomically writes a dictionary as JSON to disk using a temporary file in the same
    directory followed by os.replace to guarantee atomic replacement and prevent corruption.
    """
    target_path = Path(file_path).resolve()
    target_dir = target_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    json_text = json.dumps(data, indent=2, ensure_ascii=False)

    temp_fd, temp_file_path = tempfile.mkstemp(
        prefix=f".{target_path.name}.tmp_",
        dir=str(target_dir),
        text=True,
    )
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(json_text)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_file_path, target_path)
    except Exception as e:
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass
        logger.error(f"Failed to atomically write JSON to {target_path}: {e}")
        raise


def save_config_atomic(config_data: dict[str, Any], config_path: str | Path | None = None) -> Path:
    """Atomically updates and saves config.json on disk."""
    path = find_config_path(config_path)
    atomic_write_json(path, config_data)
    logger.info(f"Atomically saved config to {path}")
    return path


class CognitiveMemoryManager:
    """
    Cognitive Memory Manager with SQLite WAL mode and in-memory RAM caching.
    Provides sub-millisecond durable writes (<0.2ms) and 0ms RAM recall.
    Supports facts, visual diary entries, spatial landmark associations,
    personality traits, and Cloudflare D1 background sync.
    """

    save_config_atomic = staticmethod(save_config_atomic)

    def __init__(self, memory_path: str | Path | None = None) -> None:
        self.explicit_memory_path = memory_path
        self.memory_path = find_memory_path(memory_path)
        self._lock = threading.RLock()

        # Determine SQLite and optional JSON paths
        if self.memory_path.suffix.lower() == ".json":
            self.json_path: Optional[Path] = self.memory_path
            self.db_path = self.memory_path.with_suffix(".db")
        else:
            self.db_path = (
                self.memory_path.with_suffix(".db")
                if self.memory_path.suffix.lower() != ".db"
                else self.memory_path
            )
            candidate_json = self.db_path.parent / DEFAULT_MEMORY_JSON_FILENAME
            self.json_path = candidate_json if candidate_json.exists() else None

        # Zero-latency RAM cache
        self.data: dict[str, Any] = {
            "version": "1.1",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "facts": [],
            "visual_diary": [],
            "landmark_memory": [],
            "personality": {},
        }

        # Initialize SQLite with WAL mode & load / migrate records
        self._init_db()
        self._load_and_migrate()

    @property
    def _data(self) -> dict[str, Any]:
        """Backward-compatibility property for callers accessing `_data`."""
        return self.data

    def _init_db(self) -> None:
        """Initializes SQLite connection with WAL mode and creates required tables."""
        with self._lock:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db_conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=10.0,
            )
            self._db_conn.row_factory = sqlite3.Row

            cur = self._db_conn.cursor()
            cur.execute("PRAGMA journal_mode = WAL;")
            cur.execute("PRAGMA synchronous = NORMAL;")
            cur.execute("PRAGMA foreign_keys = ON;")
            cur.execute("PRAGMA busy_timeout = 5000;")

            # 1. Facts Table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    category TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    synced INTEGER DEFAULT 0
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_facts_cat_key ON facts(category, key);")

            # 2. Visual Diary Table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS visual_diary (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    description TEXT NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    event_context TEXT DEFAULT '',
                    synced INTEGER DEFAULT 0
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_diary_ts ON visual_diary(timestamp);")

            # 3. Spatial Landmark Memory Table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS landmark_memory (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    landmark TEXT NOT NULL,
                    object_type TEXT NOT NULL DEFAULT 'tool',
                    dist_px REAL NOT NULL DEFAULT 0.0,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    relative_position TEXT DEFAULT '',
                    timestamp TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    synced INTEGER DEFAULT 0
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_lm_name ON landmark_memory(name);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_lm_ts ON landmark_memory(timestamp);")

            # 4. Personality Matrix Table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS personality (
                    trait TEXT PRIMARY KEY,
                    value INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    synced INTEGER DEFAULT 0
                );
                """
            )
            self._db_conn.commit()

    def _load_and_migrate(self) -> None:
        """Loads records into RAM cache, migrating from JSON if database is new or empty."""
        with self._lock:
            cur = self._db_conn.cursor()

            cur.execute("SELECT COUNT(*) FROM facts")
            facts_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM visual_diary")
            diary_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM landmark_memory")
            lm_count = cur.fetchone()[0]

            total_records = facts_count + diary_count + lm_count

            # If SQLite has 0 records, check if we can migrate from JSON
            if total_records == 0:
                json_candidates: list[Path] = []
                if self.json_path and self.json_path.is_file():
                    json_candidates.append(self.json_path)
                if self.explicit_memory_path is None:
                    default_json = Path(__file__).resolve().parent.parent / DEFAULT_MEMORY_JSON_FILENAME
                    if default_json.is_file() and default_json not in json_candidates:
                        json_candidates.append(default_json)

                for j_file in json_candidates:
                    try:
                        with open(j_file, "r", encoding="utf-8") as f:
                            raw = json.load(f)
                        if isinstance(raw, dict):
                            now_iso = datetime.now(timezone.utc).isoformat()
                            for f_item in raw.get("facts", []):
                                f_id = f_item.get("id") or f"fact_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
                                cur.execute(
                                    """
                                    INSERT OR REPLACE INTO facts (id, timestamp, category, key, value, fact, synced)
                                    VALUES (?, ?, ?, ?, ?, ?, 0)
                                    """,
                                    (
                                        f_id,
                                        f_item.get("timestamp", now_iso),
                                        f_item.get("category", "general"),
                                        f_item.get("key", ""),
                                        f_item.get("value", ""),
                                        f_item.get("fact", ""),
                                    ),
                                )

                            for d_item in raw.get("visual_diary", []):
                                d_id = d_item.get("id") or f"diary_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
                                tags_str = json.dumps(d_item.get("tags", []))
                                cur.execute(
                                    """
                                    INSERT OR REPLACE INTO visual_diary (id, timestamp, description, tags_json, event_context, synced)
                                    VALUES (?, ?, ?, ?, ?, 0)
                                    """,
                                    (
                                        d_id,
                                        d_item.get("timestamp", now_iso),
                                        d_item.get("description", ""),
                                        tags_str,
                                        d_item.get("event_context", ""),
                                    ),
                                )

                            for l_item in raw.get("landmark_memory", []):
                                l_id = l_item.get("id") or f"landmark_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
                                meta_str = json.dumps(l_item.get("metadata", {}))
                                cur.execute(
                                    """
                                    INSERT OR REPLACE INTO landmark_memory
                                    (id, name, landmark, object_type, dist_px, confidence, relative_position, timestamp, metadata_json, synced)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                                    """,
                                    (
                                        l_id,
                                        l_item.get("item_name") or l_item.get("name", "object"),
                                        l_item.get("landmark_name") or l_item.get("landmark", "unknown"),
                                        l_item.get("object_type", "tool"),
                                        float(l_item.get("dist_px", 0.0)),
                                        float(l_item.get("confidence", 1.0)),
                                        str(l_item.get("relative_position", "")),
                                        l_item.get("timestamp", now_iso),
                                        meta_str,
                                    ),
                                )

                            self._db_conn.commit()
                            logger.info(
                                f"Migrated {len(raw.get('facts', []))} facts and {len(raw.get('landmark_memory', []))} landmarks "
                                f"from {j_file} into SQLite WAL database {self.db_path}."
                            )
                            break
                    except Exception as e:
                        logger.warning(f"Could not load/migrate from JSON {j_file} ({e}); starting with clean database.")

            # Hydrate in-memory RAM cache from SQLite
            cur.execute("SELECT id, timestamp, category, key, value, fact FROM facts ORDER BY timestamp ASC")
            self.data["facts"] = [
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "category": row["category"],
                    "key": row["key"],
                    "value": row["value"],
                    "fact": row["fact"],
                }
                for row in cur.fetchall()
            ]

            cur.execute("SELECT id, timestamp, description, tags_json, event_context FROM visual_diary ORDER BY timestamp ASC")
            self.data["visual_diary"] = []
            for row in cur.fetchall():
                try:
                    tags = json.loads(row["tags_json"] or "[]")
                except Exception:
                    tags = []
                entry = {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "description": row["description"],
                    "tags": tags,
                }
                if row["event_context"]:
                    entry["event_context"] = row["event_context"]
                self.data["visual_diary"].append(entry)

            cur.execute(
                """
                SELECT id, name, landmark, object_type, dist_px, confidence, relative_position, timestamp, metadata_json
                FROM landmark_memory ORDER BY timestamp ASC
                """
            )
            self.data["landmark_memory"] = []
            for row in cur.fetchall():
                try:
                    meta = json.loads(row["metadata_json"] or "{}")
                except Exception:
                    meta = {}
                self.data["landmark_memory"].append({
                    "id": row["id"],
                    "item_name": row["name"],
                    "landmark_name": row["landmark"],
                    "object_type": row["object_type"],
                    "dist_px": row["dist_px"],
                    "confidence": row["confidence"],
                    "relative_position": row["relative_position"],
                    "timestamp": row["timestamp"],
                    "metadata": meta,
                })

            cur.execute("SELECT trait, value FROM personality")
            self.data["personality"] = {row["trait"]: row["value"] for row in cur.fetchall()}

            # If caller explicitly provided a .json path (e.g. unit tests checking json on disk), sync it
            if self.memory_path.suffix.lower() == ".json" and not self.memory_path.is_file():
                self._save_json()

    def _save_json(self) -> None:
        """Atomically flushes RAM cache to JSON for test or export compatibility."""
        target_path = self.json_path or self.memory_path
        if target_path and target_path.suffix.lower() == ".json":
            try:
                atomic_write_json(target_path, self.data)
            except Exception as e:
                logger.warning(f"Failed to update JSON mirror at {target_path}: {e}")

    def export_to_json(self, target_path: str | Path) -> None:
        """Exports the current in-memory RAM cache state to a JSON file."""
        with self._lock:
            atomic_write_json(Path(target_path), self.data)

    def save_fact(
        self,
        category: str,
        key: str,
        value: str,
        fact_text: str | None = None,
    ) -> dict[str, Any]:
        """
        Stores or updates a declarative fact in RAM cache and SQLite WAL database (<0.2ms).
        If a fact with the same category and key exists, it is updated in-place.
        """
        category_clean = str(category or "general").strip()
        key_clean = str(key or "").strip()
        value_clean = str(value or "").strip()
        fact_str = (
            str(fact_text).strip()
            if fact_text
            else (f"{key_clean}: {value_clean}" if key_clean and value_clean else (value_clean or key_clean))
        )

        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            existing_fact = None
            if key_clean:
                for f in self.data["facts"]:
                    if (
                        str(f.get("category", "")).strip().lower() == category_clean.lower()
                        and str(f.get("key", "")).strip().lower() == key_clean.lower()
                    ):
                        existing_fact = f
                        break

            cur = self._db_conn.cursor()
            if existing_fact:
                existing_fact["value"] = value_clean
                existing_fact["fact"] = fact_str
                existing_fact["timestamp"] = now_iso
                fact_id = existing_fact.get("id", f"fact_{int(time.time() * 1000)}")
                cur.execute(
                    """
                    UPDATE facts
                    SET value = ?, fact = ?, timestamp = ?, synced = 0
                    WHERE id = ?
                    """,
                    (value_clean, fact_str, now_iso, fact_id),
                )
            else:
                fact_id = f"fact_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
                new_fact = {
                    "id": fact_id,
                    "timestamp": now_iso,
                    "category": category_clean,
                    "key": key_clean,
                    "value": value_clean,
                    "fact": fact_str,
                }
                self.data["facts"].append(new_fact)
                cur.execute(
                    """
                    INSERT INTO facts (id, timestamp, category, key, value, fact, synced)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                    """,
                    (fact_id, now_iso, category_clean, key_clean, value_clean, fact_str),
                )

            self._db_conn.commit()
            if self.memory_path.suffix.lower() == ".json":
                self._save_json()

            logger.info(f"Saved fact [{category_clean}] {key_clean}='{value_clean}' to memory.")

            return {
                "status": "success",
                "id": fact_id,
                "category": category_clean,
                "key": key_clean,
                "value": value_clean,
                "fact": fact_str,
                "timestamp": now_iso,
            }

    def log_visual_diary_entry(
        self,
        description: str,
        tags: list[str] | str | None = None,
        event_context: str | None = None,
    ) -> dict[str, Any]:
        """
        Appends an observation to RAM cache and SQLite WAL database (<0.2ms).
        """
        desc_clean = str(description or "").strip()
        if isinstance(tags, str):
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        elif isinstance(tags, (list, tuple)):
            tag_list = [str(t).strip() for t in tags if str(t).strip()]
        else:
            tag_list = []

        now_iso = datetime.now(timezone.utc).isoformat()
        diary_id = f"diary_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"

        entry: dict[str, Any] = {
            "id": diary_id,
            "timestamp": now_iso,
            "description": desc_clean,
            "tags": tag_list,
        }
        if event_context:
            entry["event_context"] = str(event_context).strip()

        with self._lock:
            self.data["visual_diary"].append(entry)

            cur = self._db_conn.cursor()
            cur.execute(
                """
                INSERT INTO visual_diary (id, timestamp, description, tags_json, event_context, synced)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (diary_id, now_iso, desc_clean, json.dumps(tag_list), str(event_context or "").strip()),
            )
            self._db_conn.commit()
            if self.memory_path.suffix.lower() == ".json":
                self._save_json()

            logger.info(f"Logged visual diary entry ({diary_id}): '{desc_clean}' [tags: {tag_list}]")

            return {
                "status": "success",
                "id": diary_id,
                "description": desc_clean,
                "tags": tag_list,
                "timestamp": now_iso,
            }

    def log_landmark_sighting(
        self,
        item_name: str,
        landmark_name: str,
        dist_px: float,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
        relative_position: str = "",
    ) -> dict[str, Any]:
        """
        Appends a spatial landmark sighting memory to RAM cache and SQLite WAL database (<0.2ms).
        """
        item_clean = str(item_name or "").strip()
        landmark_clean = str(landmark_name or "").strip()
        dist_val = float(dist_px)
        conf_val = float(confidence)
        now_iso = datetime.now(timezone.utc).isoformat()
        landmark_id = f"landmark_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        meta_dict = metadata if isinstance(metadata, dict) else {}

        entry: dict[str, Any] = {
            "id": landmark_id,
            "item_name": item_clean,
            "landmark_name": landmark_clean,
            "dist_px": dist_val,
            "confidence": conf_val,
            "relative_position": str(relative_position or "").strip(),
            "timestamp": now_iso,
            "metadata": meta_dict,
        }

        with self._lock:
            if "landmark_memory" not in self.data:
                self.data["landmark_memory"] = []
            self.data["landmark_memory"].append(entry)

            cur = self._db_conn.cursor()
            cur.execute(
                """
                INSERT INTO landmark_memory
                (id, name, landmark, object_type, dist_px, confidence, relative_position, timestamp, metadata_json, synced)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    landmark_id,
                    item_clean,
                    landmark_clean,
                    str(meta_dict.get("object_type", "tool")),
                    dist_val,
                    conf_val,
                    str(relative_position or "").strip(),
                    now_iso,
                    json.dumps(meta_dict),
                ),
            )
            self._db_conn.commit()
            if self.memory_path.suffix.lower() == ".json":
                self._save_json()

            logger.info(
                f"Logged spatial landmark memory ({landmark_id}): '{item_clean}' near '{landmark_clean}' ({dist_val:.1f}px, conf={conf_val:.2f})"
            )

            return {
                "status": "success",
                "id": landmark_id,
                "item_name": item_clean,
                "landmark_name": landmark_clean,
                "dist_px": dist_val,
                "confidence": conf_val,
                "timestamp": now_iso,
            }

    def record_landmark(
        self,
        name: str,
        landmark: str,
        object_type: str = "tool",
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
        dist_px: float = 0.0,
    ) -> str:
        """Convenience method for recording spatial landmark memory."""
        meta = metadata.copy() if isinstance(metadata, dict) else {}
        meta["object_type"] = object_type
        res = self.log_landmark_sighting(
            item_name=name,
            landmark_name=landmark,
            dist_px=dist_px,
            confidence=confidence,
            metadata=meta,
        )
        return str(res.get("id", ""))

    def update_personality(self, matrix: dict[str, Any]) -> bool:
        """
        Updates personality traits in RAM cache and SQLite WAL database (<0.2ms).
        """
        if not isinstance(matrix, dict):
            return False
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            if "personality" not in self.data:
                self.data["personality"] = {}
            cur = self._db_conn.cursor()
            for k, v in matrix.items():
                if isinstance(v, (int, float)):
                    int_val = int(max(0, min(100, round(v))))
                    trait_key = str(k).lower().strip()
                    self.data["personality"][trait_key] = int_val
                    cur.execute(
                        """
                        INSERT OR REPLACE INTO personality (trait, value, updated_at, synced)
                        VALUES (?, ?, ?, 0)
                        """,
                        (trait_key, int_val, now_iso),
                    )
            self._db_conn.commit()
        return True

    def set_personality_trait(self, trait: str, value: int) -> None:
        """Updates a single personality trait in RAM cache and SQLite."""
        self.update_personality({trait: value})

    def get_personality(self) -> dict[str, int]:
        """Returns all personality traits directly from RAM cache (0ms)."""
        with self._lock:
            return dict(self.data.get("personality", {}))

    def query_landmark_locations(self, item_name: str = "") -> list[dict[str, Any]]:
        """
        Performs 0ms timestamped spatial recall from RAM cache for a specific item
        or returns all recorded landmark associations in reverse chronological order.
        """
        item_clean = str(item_name or "").strip().lower()
        with self._lock:
            landmarks = self.data.get("landmark_memory", [])
            if not item_clean:
                return [dict(e) for e in reversed(landmarks)]

            matches: list[dict[str, Any]] = []
            for entry in reversed(landmarks):
                entry_item = str(entry.get("item_name", "")).lower()
                entry_landmark = str(entry.get("landmark_name", "")).lower()
                if item_clean in entry_item or item_clean in entry_landmark:
                    matches.append(dict(entry))
            return matches

    def query_memory(
        self,
        query: str = "",
        category: str | None = None,
    ) -> dict[str, Any]:
        """
        Performs 0ms multi-criteria search in RAM cache across facts, diary, and landmarks.
        """
        q_lower = str(query or "").strip().lower()
        cat_lower = str(category).strip().lower() if category else None

        with self._lock:
            matched_facts: list[dict[str, Any]] = []
            for f in self.data.get("facts", []):
                f_cat = str(f.get("category", "")).lower()
                if cat_lower and f_cat != cat_lower:
                    continue

                if not q_lower:
                    matched_facts.append(dict(f))
                else:
                    k = str(f.get("key", "")).lower()
                    v = str(f.get("value", "")).lower()
                    text = str(f.get("fact", "")).lower()
                    if q_lower in k or q_lower in v or q_lower in text or q_lower in f_cat:
                        matched_facts.append(dict(f))

            matched_diary: list[dict[str, Any]] = []
            search_diary = (
                cat_lower is None
                or cat_lower in ["visual", "diary", "vision", "observation", "event", "inauguration"]
            )
            if search_diary:
                for entry in self.data.get("visual_diary", []):
                    if not q_lower:
                        matched_diary.append(dict(entry))
                    else:
                        desc = str(entry.get("description", "")).lower()
                        tags = [str(t).lower() for t in entry.get("tags", [])]
                        ctx = str(entry.get("event_context", "")).lower()
                        if q_lower in desc or q_lower in ctx or any(q_lower in t for t in tags):
                            matched_diary.append(dict(entry))

            matched_landmarks: list[dict[str, Any]] = []
            search_landmarks = cat_lower is None or cat_lower in ["landmark", "spatial", "location", "object"]
            if search_landmarks:
                for lm in self.data.get("landmark_memory", []):
                    if not q_lower:
                        matched_landmarks.append(dict(lm))
                    else:
                        item = str(lm.get("item_name", "")).lower()
                        lnd = str(lm.get("landmark_name", "")).lower()
                        rel = str(lm.get("relative_position", "")).lower()
                        if q_lower in item or q_lower in lnd or q_lower in rel:
                            matched_landmarks.append(dict(lm))

            return {
                "status": "success",
                "query": query,
                "category": category,
                "facts": matched_facts,
                "visual_diary": matched_diary,
                "landmark_memory": matched_landmarks,
                "results": matched_facts + matched_diary + matched_landmarks,
                "total_matches": len(matched_facts) + len(matched_diary) + len(matched_landmarks),
            }

    def get_boot_recall_context(self) -> str:
        """
        Builds long-term memory prompt markdown directly from RAM cache (0ms)
        to inject into Gemini Live system instructions on boot.
        """
        with self._lock:
            facts = self.data.get("facts", [])
            diary = self.data.get("visual_diary", [])
            landmarks = self.data.get("landmark_memory", [])

            if not facts and not diary and not landmarks:
                return ""

            lines = ["## Long-Term Memory (Cognitive Diary):"]

            if facts:
                lines.append("### Recalled Facts:")
                for f in facts:
                    cat = f.get("category", "general")
                    k = f.get("key", "")
                    v = f.get("value", "")
                    fact_str = f.get("fact", "")
                    if k and v and fact_str and fact_str != f"{k}: {v}":
                        lines.append(f"- [{cat}] {k}: {v} ({fact_str})")
                    elif k and v:
                        lines.append(f"- [{cat}] {k}: {v}")
                    elif fact_str:
                        lines.append(f"- [{cat}] {fact_str}")
                    elif v:
                        lines.append(f"- [{cat}] {v}")

            if diary:
                lines.append("### Recent Visual Diary:")
                for entry in diary[-10:]:
                    desc = entry.get("description", "")
                    tags = entry.get("tags", [])
                    ts = entry.get("timestamp", "")
                    tag_str = f" [tags: {', '.join(tags)}]" if tags else ""
                    lines.append(f"- [{ts}] {desc}{tag_str}")

            if landmarks:
                lines.append("### Spatial Landmark Locations:")
                for lm in landmarks[-10:]:
                    item = lm.get("item_name", "object")
                    landmark = lm.get("landmark_name", "unknown")
                    dist = lm.get("dist_px", 0.0)
                    ts = lm.get("timestamp", "")
                    lines.append(f"- [{ts}] {item} near {landmark} ({dist:.0f}px)")

            return "\n".join(lines)

    def get_all_facts(self) -> list[dict[str, Any]]:
        """Returns all facts from RAM cache (0ms)."""
        with self._lock:
            return [dict(f) for f in self.data.get("facts", [])]

    def get_unsynced_records(self) -> dict[str, list[dict[str, Any]]]:
        """
        Queries all records marked `synced = 0` across SQLite tables for Cloudflare D1 sync.
        """
        with self._lock:
            cur = self._db_conn.cursor()

            cur.execute("SELECT id, timestamp, category, key, value, fact FROM facts WHERE synced = 0")
            facts = [dict(r) for r in cur.fetchall()]

            cur.execute("SELECT id, timestamp, description, tags_json, event_context FROM visual_diary WHERE synced = 0")
            diary = [dict(r) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT id, name, landmark, object_type, dist_px, confidence, relative_position, timestamp, metadata_json
                FROM landmark_memory WHERE synced = 0
                """
            )
            landmarks = [dict(r) for r in cur.fetchall()]

            cur.execute("SELECT trait, value, updated_at FROM personality WHERE synced = 0")
            personality = [dict(r) for r in cur.fetchall()]

            return {
                "facts": facts,
                "visual_diary": diary,
                "landmark_memory": landmarks,
                "personality": personality,
            }

    def mark_records_synced(self, table: str, ids: list[str]) -> None:
        """Marks a batch of primary keys as synced = 1 in SQLite."""
        if not ids:
            return
        allowed_tables = {"facts", "visual_diary", "landmark_memory", "personality"}
        if table not in allowed_tables:
            return
        with self._lock:
            cur = self._db_conn.cursor()
            id_col = "trait" if table == "personality" else "id"
            placeholders = ",".join("?" for _ in ids)
            cur.execute(f"UPDATE {table} SET synced = 1 WHERE {id_col} IN ({placeholders})", ids)
            self._db_conn.commit()

    def close(self) -> None:
        """Closes SQLite database connection cleanly."""
        with self._lock:
            if hasattr(self, "_db_conn") and self._db_conn:
                try:
                    self._db_conn.commit()
                    self._db_conn.close()
                except Exception:
                    pass

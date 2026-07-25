from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime

from services.common.contracts import Tier, tier_name


class PolicyStore:
    def __init__(self, db_path: str):
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.db_path = db_path
        self._init()

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_policy_state (
                  agent_id TEXT PRIMARY KEY,
                  current_tier INTEGER NOT NULL,
                  policy_version INTEGER NOT NULL DEFAULT 1,
                  last_demoted_at TEXT,
                  last_alert_id TEXT,
                  last_demote_reason TEXT
                );
                CREATE TABLE IF NOT EXISTS policy_events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  agent_id TEXT NOT NULL,
                  event_type TEXT NOT NULL,
                  from_tier INTEGER,
                  to_tier INTEGER,
                  alert_id TEXT,
                  reason TEXT,
                  created_at TEXT NOT NULL
                );
                """
            )

    def get(self, agent_id: str) -> dict:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM agent_policy_state WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO agent_policy_state(agent_id, current_tier) VALUES (?, ?)",
                    (agent_id, int(Tier.T3)),
                )
                return {
                    "agent_id": agent_id,
                    "current_tier": tier_name(Tier.T3),
                    "policy_version": 1,
                    "last_demoted_at": None,
                    "last_alert_id": None,
                    "last_demote_reason": None,
                }
            result = dict(row)
            result["current_tier"] = tier_name(result["current_tier"])
            return result

    def demote(self, agent_id: str, target_tier: Tier, alert_id: str, reason: str) -> dict:
        before = self.get(agent_id)
        # Alert delivery is at-least-once. Retrying the same alert must not
        # create a new policy version or obscure the original evidence.
        if before["last_alert_id"] == alert_id:
            return before
        before_tier = Tier(int(before["current_tier"][1:]))
        now = datetime.now(UTC).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE agent_policy_state
                   SET current_tier = ?, policy_version = policy_version + 1,
                       last_demoted_at = ?, last_alert_id = ?, last_demote_reason = ?
                 WHERE agent_id = ?
                """,
                (int(target_tier), now, alert_id, reason, agent_id),
            )
            conn.execute(
                """
                INSERT INTO policy_events(agent_id, event_type, from_tier, to_tier, alert_id, reason, created_at)
                VALUES (?, 'demotion', ?, ?, ?, ?, ?)
                """,
                (agent_id, int(before_tier), int(target_tier), alert_id, reason, now),
            )
        return self.get(agent_id)

    def reset(self, agent_id: str) -> dict:
        now = datetime.now(UTC).isoformat()
        before = self.get(agent_id)
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE agent_policy_state
                   SET current_tier = ?, policy_version = policy_version + 1,
                       last_demoted_at = NULL, last_alert_id = NULL, last_demote_reason = NULL
                 WHERE agent_id = ?
                """,
                (int(Tier.T3), agent_id),
            )
            conn.execute(
                """
                INSERT INTO policy_events(agent_id, event_type, from_tier, to_tier, created_at)
                VALUES (?, 'manual_reset', ?, ?, ?)
                """,
                (agent_id, int(before["current_tier"][1:]), int(Tier.T3), now),
            )
        return self.get(agent_id)

    def get_events(self, agent_id: str, limit: int = 50) -> list[dict]:
        """Return the most recent policy events for an agent."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM policy_events WHERE agent_id = ? ORDER BY id DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]

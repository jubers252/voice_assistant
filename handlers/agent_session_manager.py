import sqlite3
import json
from dataclasses import asdict
from typing import Optional, List, Any
from strands.session.session_repository import SessionRepository
from strands.types.session import Session, SessionAgent, SessionMessage

class MySQLiteRepository(SessionRepository):
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._bootstrap()

    def _bootstrap(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS strands_store (
                    key TEXT PRIMARY KEY,
                    data TEXT,
                    created_at DATETIME DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%f', 'NOW'))
                )
            """)

    # --- SESSION METHODS ---
    def create_session(self, session: Session) -> Session:
        self._write(f"session_{session.session_id}", asdict(session))
        return session

    def read_session(self, session_id: str, **kwargs) -> Optional[Session]:
        data = self._read(f"session_{session_id}")
        return Session.from_dict(data) if data else None

    def update_session(self, session: Session, **kwargs) -> Session:
        self._write(f"session_{session.session_id}", asdict(session))
        return session
    
    def delete_session(self, session_id: str, **kwargs) -> None:
        self._delete(f"session_{session_id}")

    # --- AGENT METHODS ---
    def create_agent(self, session_id: str, session_agent: SessionAgent, **kwargs) -> None:
        self._write(f"agent_{session_id}_{session_agent.agent_id}", asdict(session_agent))

    def read_agent(self, session_id: str, agent_id: str, **kwargs) -> Optional[SessionAgent]:
        data = self._read(f"agent_{session_id}_{agent_id}")
        return SessionAgent.from_dict(data) if data else None

    def update_agent(self, session_id: str, session_agent: SessionAgent, **kwargs) -> None:
        self._write(f"agent_{session_id}_{session_agent.agent_id}", asdict(session_agent))

    # --- MESSAGE METHODS ---
    def create_message(self, session_id: str, agent_id: str, session_message: SessionMessage, **kwargs) -> None:
        self._write(f"msg_{session_id}_{agent_id}_{session_message.message_id}", asdict(session_message))
        self._prune_old_messages(session_id, agent_id, limit=100)


    def read_message(self, session_id: str, agent_id: str, message_id: str, **kwargs) -> Optional[SessionMessage]:
        data = self._read(f"msg_{session_id}_{agent_id}_{message_id}")
        return SessionMessage.from_dict(data) if data else None


    def update_message(self, session_id: str, agent_id: str, session_message: SessionMessage, **kwargs) -> None:
        self._write(f"msg_{session_id}_{agent_id}_{session_message.message_id}", asdict(session_message))


    def list_messages(self, session_id: str, agent_id: str, **kwargs) -> List[SessionMessage]:
        with sqlite3.connect(self.db_path) as conn:
            # Sort by created_at to maintain the Tool -> Result chain
            cursor = conn.execute(
                "SELECT data FROM strands_store WHERE key LIKE ? ORDER BY created_at ASC", 
                (f"msg_{session_id}_{agent_id}_%",)
            )
            return [SessionMessage.from_dict(json.loads(row[0])) for row in cursor.fetchall()]

    # --- HELPERS ---
    def _write(self, key: str, data: dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO strands_store (key, data) VALUES (?, ?)", (key, json.dumps(data)))

    def _read(self, key: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT data FROM strands_store WHERE key = ?", (key,)).fetchone()
            return json.loads(row[0]) if row else None
            
    def _delete(self, key: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM strands_store WHERE key = ?", (key,))

    def _prune_old_messages(self, session_id, agent_id, limit=100):
        """Atomic cleanup to keep the SQLite DB small."""
        prefix = f"msg_{session_id}_{agent_id}_%"
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"""
                DELETE FROM strands_store 
                WHERE key LIKE ? 
                AND key NOT IN (
                    SELECT key FROM strands_store 
                    WHERE key LIKE ? 
                    ORDER BY created_at DESC 
                    LIMIT {limit}
                )
            """, (prefix, prefix))
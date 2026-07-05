"""SQLite schema and CRUD operations."""
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

from src.config import CONFIG

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
-- Companies table
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    domain TEXT,
    industry TEXT,
    size TEXT,
    location TEXT,
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, domain)
);

-- Contacts table
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    name TEXT,
    title TEXT,
    email TEXT,
    email_valid INTEGER DEFAULT 0,
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- Leads table (enriched + scored)
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    contact_id INTEGER,
    completeness_score REAL DEFAULT 0,
    source_reliability REAL DEFAULT 0,
    email_validity REAL DEFAULT 0,
    relevance_score REAL DEFAULT 0,
    total_score REAL DEFAULT 0,
    status TEXT DEFAULT 'new',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies(id),
    FOREIGN KEY (contact_id) REFERENCES contacts(id)
);

-- Sources tracking
CREATE TABLE IF NOT EXISTS source_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT,
    records_scraped INTEGER DEFAULT 0,
    records_inserted INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    started_at TEXT,
    finished_at TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_companies_domain ON companies(domain);
CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name);
CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(total_score);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
"""


class Database:
    """SQLite database manager with connection pooling."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or CONFIG["database"]["path"]
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Initialize schema."""
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
        logger.info("Database initialized: %s", self.db_path)

    # ---- Companies ----

    def insert_company(self, company: Dict[str, Any]) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO companies
                   (name, domain, industry, size, location, source)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    company.get("name"),
                    company.get("domain"),
                    company.get("industry"),
                    company.get("size"),
                    company.get("location"),
                    company.get("source"),
                ),
            )
            if cur.lastrowid:
                return cur.lastrowid
            # Return existing
            row = conn.execute(
                "SELECT id FROM companies WHERE name = ? AND domain = ?",
                (company.get("name"), company.get("domain")),
            ).fetchone()
            return row["id"] if row else 0

    def get_company_by_id(self, company_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM companies WHERE id = ?", (company_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_all_companies(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM companies").fetchall()
            return [dict(r) for r in rows]

    # ---- Contacts ----

    def insert_contact(self, contact: Dict[str, Any]) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO contacts
                   (company_id, name, title, email, email_valid, source)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    contact.get("company_id"),
                    contact.get("name"),
                    contact.get("title"),
                    contact.get("email"),
                    contact.get("email_valid", 0),
                    contact.get("source"),
                ),
            )
            return cur.lastrowid

    def get_contacts_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM contacts WHERE company_id = ?", (company_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ---- Leads ----

    def insert_lead(self, lead: Dict[str, Any]) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO leads
                   (company_id, contact_id, completeness_score, source_reliability,
                    email_validity, relevance_score, total_score, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    lead.get("company_id"),
                    lead.get("contact_id"),
                    lead.get("completeness_score", 0),
                    lead.get("source_reliability", 0),
                    lead.get("email_validity", 0),
                    lead.get("relevance_score", 0),
                    lead.get("total_score", 0),
                    lead.get("status", "new"),
                ),
            )
            return cur.lastrowid

    def get_leads(self, min_score: float = 0, status: Optional[str] = None) -> List[Dict[str, Any]]:
        query = """
            SELECT l.*,
                   c.name as company_name, c.domain, c.industry, c.size, c.location,
                   co.name as contact_name, co.title as contact_title, co.email as contact_email
            FROM leads l
            JOIN companies c ON l.company_id = c.id
            LEFT JOIN contacts co ON l.contact_id = co.id
            WHERE l.total_score >= ?
        """
        params = [min_score]
        if status:
            query += " AND l.status = ?"
            params.append(status)
        query += " ORDER BY l.total_score DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def update_lead_status(self, lead_id: int, status: str):
        with self._connect() as conn:
            conn.execute(
                "UPDATE leads SET status = ? WHERE id = ?", (status, lead_id)
            )

    def get_stats(self) -> Dict[str, Any]:
        with self._connect() as conn:
            companies = conn.execute(
                "SELECT COUNT(*) as count FROM companies"
            ).fetchone()["count"]
            contacts = conn.execute(
                "SELECT COUNT(*) as count FROM contacts"
            ).fetchone()["count"]
            leads = conn.execute(
                "SELECT COUNT(*) as count FROM leads"
            ).fetchone()["count"]
            avg_score = conn.execute(
                "SELECT AVG(total_score) as avg FROM leads"
            ).fetchone()["avg"] or 0
            high_quality = conn.execute(
                "SELECT COUNT(*) as count FROM leads WHERE total_score >= 70"
            ).fetchone()["count"]
            return {
                "companies": companies,
                "contacts": contacts,
                "leads": leads,
                "avg_score": round(avg_score, 2),
                "high_quality_leads": high_quality,
            }

    # ---- Source Logs ----

    def log_source_run(self, log: Dict[str, Any]) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO source_logs
                   (source_name, records_scraped, records_inserted, errors, started_at, finished_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    log.get("source_name"),
                    log.get("records_scraped", 0),
                    log.get("records_inserted", 0),
                    log.get("errors", 0),
                    log.get("started_at"),
                    log.get("finished_at"),
                ),
            )
            return cur.lastrowid

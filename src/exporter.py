"""CSV/JSON export with filtering and formatting."""
import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd

from src.config import CONFIG, EXPORTS_DIR

logger = logging.getLogger(__name__)


class Exporter:
    """Export leads to CSV or JSON with score filtering."""

    def __init__(self, output_dir: Path = EXPORTS_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def to_csv(self, leads: List[Dict[str, Any]], filename: str = None,
               min_score: float = None) -> Path:
        """Export leads to CSV with scored columns."""
        if min_score is None:
            min_score = CONFIG["export"]["min_score"]

        filtered = [l for l in leads if l.get("total_score", 0) >= min_score]
        if not filtered:
            logger.warning("No leads meet min_score threshold: %s", min_score)
            return None

        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"leads_{ts}.csv"

        path = self.output_dir / filename
        df = pd.DataFrame(filtered)

        # Reorder columns for readability
        priority_cols = [
            "total_score", "company_name", "domain", "industry", "size", "location",
            "contact_name", "contact_title", "contact_email",
            "completeness_score", "source_reliability", "email_validity", "relevance_score",
            "status",
        ]
        available = [c for c in priority_cols if c in df.columns]
        other = [c for c in df.columns if c not in priority_cols]
        df = df[available + other]

        df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
        logger.info("Exported %d leads to CSV: %s", len(filtered), path)
        return path

    def to_json(self, leads: List[Dict[str, Any]], filename: str = None,
                min_score: float = None) -> Path:
        """Export leads to JSON with full metadata."""
        if min_score is None:
            min_score = CONFIG["export"]["min_score"]

        filtered = [l for l in leads if l.get("total_score", 0) >= min_score]
        if not filtered:
            logger.warning("No leads meet min_score threshold: %s", min_score)
            return None

        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"leads_{ts}.json"

        path = self.output_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "meta": {
                    "exported_at": datetime.now().isoformat(),
                    "count": len(filtered),
                    "min_score": min_score,
                    "version": "1.0.0",
                },
                "leads": filtered,
            }, f, indent=2, ensure_ascii=False)

        logger.info("Exported %d leads to JSON: %s", len(filtered), path)
        return path

    def to_markdown(self, leads: List[Dict[str, Any]], filename: str = None,
                    min_score: float = None, top_n: int = 20) -> Path:
        """Export top-N leads to a Markdown table for quick review."""
        if min_score is None:
            min_score = CONFIG["export"]["min_score"]

        filtered = [l for l in leads if l.get("total_score", 0) >= min_score]
        filtered = sorted(filtered, key=lambda x: x.get("total_score", 0), reverse=True)[:top_n]

        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"leads_{ts}.md"

        path = self.output_dir / filename
        lines = [
            "# B2B Lead Export Report",
            "**Generated:** " + datetime.now().strftime("%Y-%m-%d %H:%M"),
            "**Min Score:** " + str(min_score) + " | **Leads Shown:** " + str(len(filtered)),
            "",
            "| Score | Company | Domain | Industry | Contact | Title | Email |",
            "|-------|---------|--------|----------|---------|-------|-------|",
        ]
        for l in filtered:
            lines.append(
                "| " + str(l.get("total_score", 0)) + " | " + str(l.get("company_name", "N/A")) + " | " +
                str(l.get("domain", "N/A")) + " | " + str(l.get("industry", "N/A")) + " | " +
                str(l.get("contact_name", "N/A")) + " | " + str(l.get("contact_title", "N/A")) + " | " +
                str(l.get("contact_email", "N/A")) + " |"
            )

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path

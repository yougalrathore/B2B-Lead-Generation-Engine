"""Fuzzy matching + entity resolution for deduplication."""
import logging
from typing import List, Dict, Any, Tuple
from urllib.parse import urlparse

from rapidfuzz import fuzz

from src.config import CONFIG
from src.storage import Database

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 85
DOMAIN_THRESHOLD = 95


class Deduplicator:
    """Entity resolution using fuzzy name matching + domain exact match."""

    def __init__(self, db: Database = None):
        self.db = db or Database()

    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalize company name for comparison."""
        if not name:
            return ""
        # Lowercase, remove common suffixes, strip punctuation
        n = name.lower().strip()
        for suffix in [", inc.", ", inc", ", llc", ", ltd.", ", ltd", ", corp.", ", corp"]:
            n = n.replace(suffix, "")
        return n.strip()

    @staticmethod
    def extract_domain(url: str) -> str:
        """Extract clean domain from URL."""
        if not url:
            return ""
        url = url.strip().lower()
        if not url.startswith("http"):
            url = "https://" + url
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.replace("www.", "")
            return domain
        except Exception:
            return url.replace("www.", "")

    def find_matches(self, company: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find potential duplicate companies in DB."""
        candidates = self.db.get_all_companies()
        matches = []
        target_name = self.normalize_name(company.get("name", ""))
        target_domain = self.extract_domain(company.get("website", ""))

        for cand in candidates:
            cand_name = self.normalize_name(cand.get("name", ""))
            cand_domain = self.extract_domain(cand.get("website", ""))

            name_score = fuzz.ratio(target_name, cand_name) if target_name and cand_name else 0
            domain_score = 100 if (target_domain and cand_domain and target_domain == cand_domain) else 0

            # Weighted confidence
            confidence = 0
            if domain_score == 100:
                confidence = 95 + (name_score / 100) * 5  # Domain match is strong signal
            elif name_score >= FUZZY_THRESHOLD:
                confidence = name_score * 0.85

            if confidence >= 80:
                matches.append({
                    "candidate": cand,
                    "name_score": round(name_score, 2),
                    "domain_score": round(domain_score, 2),
                    "confidence": round(confidence, 2),
                })

        # Sort by confidence descending
        matches.sort(key=lambda x: x["confidence"], reverse=True)
        return matches

    def merge_records(self, new_record: Dict[str, Any], existing: Dict[str, Any]) -> Dict[str, Any]:
        """Merge two company records, preferring non-null values."""
        merged = dict(existing)
        for key, value in new_record.items():
            if value and (not merged.get(key) or len(str(value)) > len(str(merged.get(key, "")))):
                merged[key] = value
        merged["_merged"] = True
        merged["_sources"] = list(set(filter(None, [existing.get("source"), new_record.get("source")])))
        return merged

    def deduplicate_batch(self, records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Process a batch: return (unique_records, duplicate_links)."""
        uniques = []
        duplicates = []
        seen_domains = {}

        for rec in records:
            domain = self.extract_domain(rec.get("website", ""))
            name = self.normalize_name(rec.get("name", ""))
            key = (name, domain) if domain else name

            # Check against already-seen in this batch
            if domain and domain in seen_domains:
                dup = seen_domains[domain]
                duplicates.append({
                    "record": rec,
                    "matched_to": dup,
                    "reason": "domain_duplicate_batch",
                })
                continue

            # Check against DB
            db_matches = self.find_matches(rec)
            if db_matches and db_matches[0]["confidence"] >= 90:
                best = db_matches[0]
                duplicates.append({
                    "record": rec,
                    "matched_to": best["candidate"],
                    "confidence": best["confidence"],
                    "reason": "db_duplicate",
                })
                continue

            uniques.append(rec)
            if domain:
                seen_domains[domain] = rec

        return uniques, duplicates

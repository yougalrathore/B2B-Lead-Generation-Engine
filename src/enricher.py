"""Cross-reference + merge logic for data enrichment."""
import logging
from typing import List, Dict, Any
from collections import defaultdict

from src.config import CONFIG
from src.deduplicator import Deduplicator

logger = logging.getLogger(__name__)


class Enricher:
    """Merge partial records from multiple sources into complete company profiles."""

    def __init__(self, deduplicator: Deduplicator = None):
        self.dedup = deduplicator or Deduplicator()

    def group_by_entity(self, records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group records by normalized company identity."""
        groups = defaultdict(list)
        for rec in records:
            domain = self.dedup.extract_domain(rec.get("website", ""))
            name = self.dedup.normalize_name(rec.get("name", ""))
            # Use domain as primary key, fallback to normalized name
            key = domain if domain else name
            if key:
                groups[key].append(rec)
        return dict(groups)

    def merge_group(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge multiple source records for the same company."""
        if not records:
            return {}

        merged = {}
        sources = []
        all_contacts = []

        for rec in records:
            sources.append(rec.get("source", "unknown"))
            # Merge company fields
            for field in ["name", "website", "industry", "size", "location"]:
                val = rec.get(field)
                if val:
                    existing = merged.get(field)
                    # Prefer longer/more specific values
                    if not existing or len(str(val)) > len(str(existing)):
                        merged[field] = val
            # Collect contacts
            if rec.get("contact_name"):
                all_contacts.append({
                    "name": rec.get("contact_name"),
                    "title": rec.get("contact_title"),
                    "email": rec.get("contact_email"),
                    "source": rec.get("source"),
                })

        merged["sources"] = list(set(sources))
        merged["contact_count"] = len(all_contacts)
        merged["contacts"] = all_contacts
        merged["enrichment_level"] = len(records)
        return merged

    def enrich_batch(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Full enrichment pipeline: group, merge, deduplicate."""
        logger.info("Enriching %d raw records...", len(records))
        groups = self.group_by_entity(records)
        enriched = []

        for key, group_records in groups.items():
            merged = self.merge_group(group_records)
            if merged:
                enriched.append(merged)
                logger.debug("Enriched entity '%s' from %d sources", key, len(group_records))

        logger.info("Enrichment complete: %d unique entities from %d records",
                    len(enriched), len(records))
        return enriched

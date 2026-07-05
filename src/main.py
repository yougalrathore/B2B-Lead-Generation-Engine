"""CLI entry point: scrape, enrich, validate, export, stats."""
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler

from src.config import CONFIG, LOGS_DIR
from src.storage import Database
from src.scraper import ScraperFactory
from src.enricher import Enricher
from src.deduplicator import Deduplicator
from src.validator import EmailValidator
from src.scorer import LeadScorer
from src.exporter import Exporter


def setup_logging():
    """Configure rotating file + console logging."""
    log_cfg = CONFIG["logging"]
    level = getattr(logging, log_cfg["level"].upper(), logging.INFO)

    logger = logging.getLogger()
    logger.setLevel(level)
    logger.handlers = []

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler
    log_path = LOGS_DIR / "leadgen.log"
    fh = RotatingFileHandler(
        log_path,
        maxBytes=log_cfg["max_bytes"],
        backupCount=log_cfg["backup_count"],
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


def run_scrape(db: Database, source_filter: list = None):
    """Run scrapers and store raw data."""
    logger = logging.getLogger(__name__)
    logger.info("=== SCRAPE PHASE ===")

    all_records = []
    scrapers = ScraperFactory.all_scrapers(db)

    for scraper in scrapers:
        if source_filter and scraper.name not in source_filter:
            continue
        try:
            records = scraper.scrape()
            all_records.extend(records)
        except Exception as e:
            logger.error("Scraper %s failed: %s", scraper.name, e)

    logger.info("Total raw records scraped: %d", len(all_records))
    return all_records


def run_enrich(records: list, db: Database):
    """Enrich and deduplicate records."""
    logger = logging.getLogger(__name__)
    logger.info("=== ENRICH + DEDUPLICATE PHASE ===")

    dedup = Deduplicator(db)
    enricher = Enricher(dedup)

    # Deduplicate first
    uniques, duplicates = dedup.deduplicate_batch(records)
    logger.info("Deduplication: %d unique, %d duplicates", len(uniques), len(duplicates))

    # Enrich by merging multi-source records
    enriched = enricher.enrich_batch(uniques)
    logger.info("Enrichment complete: %d entities", len(enriched))
    return enriched, duplicates


def run_validate_and_score(enriched: list, db: Database):
    """Validate emails, score leads, and persist to DB."""
    logger = logging.getLogger(__name__)
    logger.info("=== VALIDATE + SCORE PHASE ===")

    leads_created = 0
    for entity in enriched:
        company_data = {
            "name": entity.get("name"),
            "domain": entity.get("website"),
            "industry": entity.get("industry"),
            "size": entity.get("size"),
            "location": entity.get("location"),
            "source": ",".join(entity.get("sources", ["unknown"])),
        }
        company_id = db.insert_company(company_data)

        contacts = entity.get("contacts", [])
        if not contacts:
            # Create a placeholder contact
            contacts = [{"name": None, "title": None, "email": None, "source": "unknown"}]

        for contact in contacts:
            email = contact.get("email")
            email_result = EmailValidator.validate(email) if email else {"score": 0, "error": "No email"}

            contact_id = db.insert_contact({
                "company_id": company_id,
                "name": contact.get("name"),
                "title": contact.get("title"),
                "email": email,
                "email_valid": 1 if email_result.get("score", 0) >= 80 else 0,
                "source": contact.get("source", "unknown"),
            })

            # Use primary source for reliability score
            primary_source = entity.get("sources", ["unknown"])[0]
            scores = LeadScorer.calculate_total(
                company_data, contact, email_result, primary_source
            )

            db.insert_lead({
                "company_id": company_id,
                "contact_id": contact_id,
                **scores,
                "status": "new",
            })
            leads_created += 1

    logger.info("Created %d leads in database", leads_created)
    return leads_created


def run_export(db: Database, fmt: str = "csv", min_score: float = None):
    """Export leads to file."""
    logger = logging.getLogger(__name__)
    logger.info("=== EXPORT PHASE ===")

    if min_score is None:
        min_score = CONFIG["export"]["min_score"]

    leads = db.get_leads(min_score=min_score)
    exporter = Exporter()

    if fmt == "csv":
        path = exporter.to_csv(leads, min_score=min_score)
    elif fmt == "json":
        path = exporter.to_json(leads, min_score=min_score)
    elif fmt == "md":
        path = exporter.to_markdown(leads, min_score=min_score)
    else:
        # Export all formats
        exporter.to_csv(leads, min_score=min_score)
        exporter.to_json(leads, min_score=min_score)
        path = exporter.to_markdown(leads, min_score=min_score)

    if path:
        logger.info("Exported to: %s", path)
    return path


def run_stats(db: Database):
    """Print database statistics."""
    stats = db.get_stats()
    print("\n" + "=" * 50)
    print("  LEAD GENERATION ENGINE — STATS")
    print("=" * 50)
    print(f"  Companies in DB:      {stats['companies']}")
    print(f"  Contacts in DB:       {stats['contacts']}")
    print(f"  Total Leads:          {stats['leads']}")
    print(f"  Average Lead Score:   {stats['avg_score']}")
    print(f"  High Quality (≥70):   {stats['high_quality_leads']}")
    print("=" * 50 + "\n")
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="B2B Lead Generation Engine — Scrape, Enrich, Score, Export"
    )
    parser.add_argument("command", choices=["scrape", "enrich", "validate", "export", "stats", "pipeline"],
                        help="Command to run")
    parser.add_argument("--source", nargs="+", help="Filter by source name(s)")
    parser.add_argument("--format", choices=["csv", "json", "md", "all"], default="csv",
                        help="Export format")
    parser.add_argument("--min-score", type=float, default=None,
                        help="Minimum lead score for export")
    parser.add_argument("--db", type=str, default=None,
                        help="Path to SQLite database")

    args = parser.parse_args()

    logger = setup_logging()
    db = Database(args.db)

    if args.command == "scrape":
        records = run_scrape(db, args.source)
        print(f"Scraped {len(records)} raw records.")

    elif args.command == "pipeline":
        records = run_scrape(db, args.source)
        enriched, duplicates = run_enrich(records, db)
        run_validate_and_score(enriched, db)
        run_export(db, args.format, args.min_score)
        run_stats(db)

    elif args.command == "enrich":
        # For demo: re-enrich existing raw data would require storage of raw
        print("Enrich requires raw records. Use 'pipeline' for full flow.")

    elif args.command == "validate":
        print("Validate runs as part of pipeline. Use 'pipeline' command.")

    elif args.command == "export":
        run_export(db, args.format, args.min_score)

    elif args.command == "stats":
        run_stats(db)


if __name__ == "__main__":
    main()

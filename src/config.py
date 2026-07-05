"""Configuration loader and constants."""
import os
import yaml
from pathlib import Path
from typing import Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
EXPORTS_DIR = BASE_DIR / "exports"
CONFIG_PATH = BASE_DIR / "config.yaml"

# Ensure directories exist
for d in [DATA_DIR, LOGS_DIR, EXPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "sources": [
        {
            "name": "tech_directory",
            "url": "https://example-tech-directory.com/companies",
            "selectors": {
                "company_card": ".company-item",
                "name": ".company-name",
                "website": ".company-website",
                "industry": ".company-industry",
                "size": ".company-size",
                "location": ".company-location",
                "contact_name": ".contact-name",
                "contact_title": ".contact-title",
                "contact_email": ".contact-email",
            },
            "reliability": 0.85,
            "rate_limit": 1.0,
        },
        {
            "name": "crunchbase_sim",
            "url": "https://example-crunchbase.com/organizations",
            "selectors": {
                "company_card": ".org-card",
                "name": ".org-name",
                "website": ".org-website",
                "industry": ".org-category",
                "size": ".org-size",
                "location": ".org-location",
                "contact_name": ".founder-name",
                "contact_title": ".founder-role",
                "contact_email": ".founder-email",
            },
            "reliability": 0.90,
            "rate_limit": 1.5,
        },
        {
            "name": "industry_hub",
            "url": "https://example-industry-hub.com/members",
            "selectors": {
                "company_card": ".member-firm",
                "name": ".firm-name",
                "website": ".firm-url",
                "industry": ".firm-sector",
                "size": ".firm-headcount",
                "location": ".firm-city",
                "contact_name": ".rep-name",
                "contact_title": ".rep-position",
                "contact_email": ".rep-email",
            },
            "reliability": 0.75,
            "rate_limit": 0.8,
        },
    ],
    "validation": {
        "mx_timeout": 5,
        "disposable_domains": [
            "mailinator.com", "tempmail.com", "10minutemail.com",
            "guerrillamail.com", "throwawaymail.com", "yopmail.com",
            "fakeinbox.com", "getairmail.com", "tempinbox.com",
        ],
        "blocked_tlds": [".tk", ".ml", ".cf", ".ga"],
    },
    "scoring": {
        "weights": {
            "completeness": 0.30,
            "source_reliability": 0.30,
            "email_validity": 0.20,
            "relevance": 0.20,
        },
        "min_score": 70,
    },
    "export": {
        "default_format": "csv",
        "min_score": 70,
    },
    "database": {
        "path": str(DATA_DIR / "leads.db"),
    },
    "logging": {
        "level": "INFO",
        "max_bytes": 10_485_760,  # 10MB
        "backup_count": 5,
    },
}


def load_config(path: Path = CONFIG_PATH) -> Dict[str, Any]:
    """Load configuration from YAML or return defaults."""
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        # Deep merge with defaults
        merged = dict(DEFAULT_CONFIG)
        merged.update(user_cfg)
        return merged
    return dict(DEFAULT_CONFIG)


CONFIG = load_config()

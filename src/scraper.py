"""Multi-source scraping with requests + Playwright fallback."""
import time
import random
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.config import CONFIG
from src.storage import Database

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class BaseScraper:
    """Base scraper with retry logic, rate limiting, and logging."""

    def __init__(self, source_config: Dict[str, Any], db: Database = None):
        self.cfg = source_config
        self.name = source_config["name"]
        self.url = source_config["url"]
        self.selectors = source_config["selectors"]
        self.reliability = source_config.get("reliability", 0.5)
        self.rate_limit = source_config.get("rate_limit", 1.0)
        self.db = db or Database()
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _sleep(self):
        """Rate limit with jitter."""
        jitter = random.uniform(0.1, 0.5)
        time.sleep(self.rate_limit + jitter)

    def _fetch(self, url: str, retries: int = 3) -> Optional[str]:
        """Fetch page with exponential backoff retry."""
        for attempt in range(1, retries + 1):
            try:
                self._sleep()
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
                logger.debug("Fetched %s (status %d)", url, resp.status_code)
                return resp.text
            except requests.exceptions.HTTPError as e:
                if resp.status_code == 429:
                    wait = 2 ** attempt + random.uniform(0, 2)
                    logger.warning("Rate limited on %s, sleeping %.1fs", url, wait)
                    time.sleep(wait)
                else:
                    logger.error("HTTP error %d on %s: %s", resp.status_code, url, e)
                    return None
            except Exception as e:
                logger.error("Fetch error (attempt %d/%d) for %s: %s", attempt, retries, url, e)
                time.sleep(2 ** attempt)
        return None

    def _parse(self, html: str) -> List[Dict[str, Any]]:
        """Parse HTML using configured selectors. Override in subclasses."""
        soup = BeautifulSoup(html, "lxml")
        records = []
        cards = soup.select(self.selectors.get("company_card", ".company"))
        for card in cards:
            record = self._extract_card(card)
            if record.get("name"):
                record["source"] = self.name
                record["source_reliability"] = self.reliability
                records.append(record)
        return records

    def _extract_card(self, card) -> Dict[str, Any]:
        """Extract fields from a single card element."""
        def _text(sel):
            el = card.select_one(sel)
            return el.get_text(strip=True) if el else None

        return {
            "name": _text(self.selectors.get("name")),
            "website": _text(self.selectors.get("website")),
            "industry": _text(self.selectors.get("industry")),
            "size": _text(self.selectors.get("size")),
            "location": _text(self.selectors.get("location")),
            "contact_name": _text(self.selectors.get("contact_name")),
            "contact_title": _text(self.selectors.get("contact_title")),
            "contact_email": _text(self.selectors.get("contact_email")),
        }

    def scrape(self) -> List[Dict[str, Any]]:
        """Run full scrape. Returns list of records."""
        started = datetime.now().isoformat()
        logger.info("[%s] Starting scrape: %s", self.name, self.url)
        html = self._fetch(self.url)
        if not html:
            self.db.log_source_run({
                "source_name": self.name,
                "records_scraped": 0,
                "records_inserted": 0,
                "errors": 1,
                "started_at": started,
                "finished_at": datetime.now().isoformat(),
            })
            return []

        records = self._parse(html)
        finished = datetime.now().isoformat()
        self.db.log_source_run({
            "source_name": self.name,
            "records_scraped": len(records),
            "records_inserted": 0,  # Updated after dedup
            "errors": 0,
            "started_at": started,
            "finished_at": finished,
        })
        logger.info("[%s] Scraped %d records", self.name, len(records))
        return records


# ═══════════════════════════════════════════════════════════════
# SIMULATED SCRAPERS — Generate realistic demo data
# These simulate real directory scrapers for demonstration
# ═══════════════════════════════════════════════════════════════

TECH_COMPANIES = [
    ("CloudScale AI", "cloudscale.ai", "Artificial Intelligence / SaaS", "200-500", "San Francisco, CA",
     "Sarah Chen", "VP of Sales", "sarah.chen@cloudscale.ai"),
    ("CloudScale Technologies", "cloudscale.ai", "Cloud Infrastructure", "200-500", "San Francisco, CA",
     "Mike Ross", "CEO", "mike.ross@cloudscale.ai"),
    ("DataForge", "dataforge.io", "Data Analytics", "50-200", "Austin, TX",
     "Alex Turner", "Head of Partnerships", "alex@dataforge.io"),
    ("SecureNet Labs", "securenet.io", "Cybersecurity", "500-1000", "Boston, MA",
     "Jennifer Walsh", "Chief Revenue Officer", "j.walsh@securenet.io"),
    ("SecureNet", "securenet.io", "Network Security", "500-1000", "Boston, MA",
     "David Park", "Sales Director", "david.park@securenet.io"),
    ("FlowStack", "flowstack.dev", "Developer Tools", "20-50", "Seattle, WA",
     "Emily Nakamura", "Growth Lead", "emily@flowstack.dev"),
    ("MedSync Health", "medsync.health", "HealthTech", "1000-5000", "New York, NY",
     "Dr. James Liu", "Chief Medical Officer", "j.liu@medsync.health"),
    ("MedSync", "medsync.health", "Digital Health", "1000-5000", "New York, NY",
     "Rachel Green", "VP Business Development", "rachel@medsync.health"),
    ("PayBridge", "paybridge.com", "FinTech", "500-1000", "Chicago, IL",
     "Tom Bradley", "Enterprise Sales", "tom.b@paybridge.com"),
    ("QuantumLeap", "quantumleap.tech", "Quantum Computing", "50-200", "Palo Alto, CA",
     "Dr. Lisa Chen", "Co-Founder", "lisa@quantumleap.tech"),
    ("GreenRoute", "greenroute.co", "Logistics / Sustainability", "200-500", "Denver, CO",
     "Mark Johnson", "VP Operations", "mark.j@greenroute.co"),
    ("CodeWave", "codewave.dev", "Developer Tools", "10-50", "Remote",
     "Sam Rivera", "Founder", "sam@codewave.dev"),
    ("RetailAI", "retailai.io", "Retail Technology", "500-1000", "Los Angeles, CA",
     "Nina Patel", "Sales Manager", "nina@retailai.io"),
    ("BuildRight", "buildright.construction", "Construction Tech", "200-500", "Dallas, TX",
     "Chris O\'Brien", "Head of Sales", "chris@buildright.construction"),
    ("EduSpark", "eduspark.org", "EdTech", "50-200", "Portland, OR",
     "Amy Foster", "Director of Institutions", "amy.f@eduspark.org"),
]

CRUNCHBASE_COMPANIES = [
    ("CloudScale AI", "cloudscale.ai", "Artificial Intelligence", "201-500", "San Francisco, California",
     "Sarah Chen", "VP Sales", "sarah.chen@cloudscale.ai"),
    ("DataForge Inc.", "dataforge.io", "Analytics", "51-200", "Austin, Texas",
     "Alex Turner", "Partnerships", "alex@dataforge.io"),
    ("SecureNet Labs", "securenet.io", "Cybersecurity", "501-1000", "Boston, Massachusetts",
     "Jennifer Walsh", "CRO", "j.walsh@securenet.io"),
    ("FlowStack", "flowstack.dev", "Developer Tools", "11-50", "Seattle, Washington",
     "Emily Nakamura", "Growth", "emily@flowstack.dev"),
    ("MedSync Health Inc.", "medsync.health", "Healthcare", "1001-5000", "New York, New York",
     "Dr. James Liu", "CMO", "j.liu@medsync.health"),
    ("PayBridge Inc", "paybridge.com", "Financial Services", "501-1000", "Chicago, Illinois",
     "Tom Bradley", "Sales", "tom.b@paybridge.com"),
    ("QuantumLeap Systems", "quantumleap.tech", "Quantum Computing", "51-200", "Palo Alto, California",
     "Dr. Lisa Chen", "Co-Founder", "lisa@quantumleap.tech"),
    ("GreenRoute Logistics", "greenroute.co", "Supply Chain", "201-500", "Denver, Colorado",
     "Mark Johnson", "Operations", "mark.j@greenroute.co"),
    ("CodeWave Labs", "codewave.dev", "Software", "1-10", "Remote",
     "Sam Rivera", "CEO", "sam@codewave.dev"),
    ("RetailAI Corp", "retailai.io", "Retail", "501-1000", "Los Angeles, California",
     "Nina Patel", "Sales", "nina@retailai.io"),
    ("BuildRight Technologies", "buildright.construction", "Construction", "201-500", "Dallas, Texas",
     "Chris O\'Brien", "Sales", "chris@buildright.construction"),
    ("EduSpark Platform", "eduspark.org", "Education", "51-200", "Portland, Oregon",
     "Amy Foster", "Institutions", "amy.f@eduspark.org"),
    ("NexGen Cloud", "nexgen.cloud", "Cloud Services", "1000-5000", "San Jose, CA",
     "Robert Kim", "VP Enterprise", "robert@nexgen.cloud"),
    ("FinFlow", "finflow.io", "FinTech", "200-500", "Miami, FL",
     "Laura Martinez", "Head of Sales", "laura@finflow.io"),
    ("AutoPilot AI", "autopilot.ai", "Automotive", "500-1000", "Detroit, MI",
     "Kevin Zhang", "Sales Director", "kevin@autopilot.ai"),
]

INDUSTRY_HUB_COMPANIES = [
    ("CloudScale", "cloudscale.ai", "AI / Machine Learning", "200-500", "SF, CA",
     "Sarah Chen", "Sales VP", "sarah.chen@cloudscale.ai"),
    ("DataForge Analytics", "dataforge.io", "Big Data", "50-200", "Austin, TX",
     "Alex Turner", "Partnerships Lead", "alex@dataforge.io"),
    ("SecureNet", "securenet.io", "InfoSec", "500-1000", "Boston, MA",
     "Jennifer Walsh", "Revenue Chief", "j.walsh@securenet.io"),
    ("FlowStack Tools", "flowstack.dev", "DevTools", "20-50", "Seattle, WA",
     "Emily Nakamura", "Growth", "emily@flowstack.dev"),
    ("MedSync", "medsync.health", "Health Tech", "1000+", "NYC, NY",
     "Dr. James Liu", "Medical Officer", "j.liu@medsync.health"),
    ("PayBridge Payments", "paybridge.com", "Payments", "500-1000", "Chicago, IL",
     "Tom Bradley", "Enterprise", "tom.b@paybridge.com"),
    ("QuantumLeap", "quantumleap.tech", "Quantum", "50-200", "Palo Alto, CA",
     "Dr. Lisa Chen", "Founder", "lisa@quantumleap.tech"),
    ("GreenRoute", "greenroute.co", "Green Logistics", "200-500", "Denver, CO",
     "Mark Johnson", "Ops VP", "mark.j@greenroute.co"),
    ("CodeWave", "codewave.dev", "Software Dev", "10-50", "Remote",
     "Sam Rivera", "Founder", "sam@codewave.dev"),
    ("RetailAI", "retailai.io", "Retail Tech", "500-1000", "LA, CA",
     "Nina Patel", "Sales Mgr", "nina@retailai.io"),
    ("BuildRight", "buildright.construction", "PropTech", "200-500", "Dallas, TX",
     "Chris O\'Brien", "Sales Head", "chris@buildright.construction"),
    ("EduSpark", "eduspark.org", "EdTech", "50-200", "Portland, OR",
     "Amy Foster", "Dir. Institutions", "amy.f@eduspark.org"),
    ("NexGen", "nexgen.cloud", "Cloud", "1000+", "San Jose, CA",
     "Robert Kim", "Enterprise VP", "robert@nexgen.cloud"),
    ("FinFlow", "finflow.io", "Finance Tech", "200-500", "Miami, FL",
     "Laura Martinez", "Sales Head", "laura@finflow.io"),
    ("AutoPilot", "autopilot.ai", "Auto AI", "500-1000", "Detroit, MI",
     "Kevin Zhang", "Dir. Sales", "kevin@autopilot.ai"),
]


class SimulatedTechDirectoryScraper(BaseScraper):
    """Simulated scraper for tech directory."""

    def scrape(self) -> List[Dict[str, Any]]:
        logger.info("[%s] Simulating scrape from tech directory...", self.name)
        records = []
        for name, domain, industry, size, location, c_name, c_title, c_email in TECH_COMPANIES:
            records.append({
                "name": name,
                "website": f"https://{domain}",
                "industry": industry,
                "size": size,
                "location": location,
                "contact_name": c_name,
                "contact_title": c_title,
                "contact_email": c_email,
                "source": self.name,
                "source_reliability": self.reliability,
            })
        time.sleep(0.5)
        logger.info("[%s] Simulated %d records", self.name, len(records))
        return records


class SimulatedCrunchbaseScraper(BaseScraper):
    """Simulated scraper for Crunchbase-style data."""

    def scrape(self) -> List[Dict[str, Any]]:
        logger.info("[%s] Simulating scrape from Crunchbase...", self.name)
        records = []
        for name, domain, industry, size, location, c_name, c_title, c_email in CRUNCHBASE_COMPANIES:
            records.append({
                "name": name,
                "website": f"https://{domain}",
                "industry": industry,
                "size": size,
                "location": location,
                "contact_name": c_name,
                "contact_title": c_title,
                "contact_email": c_email,
                "source": self.name,
                "source_reliability": self.reliability,
            })
        time.sleep(0.8)
        logger.info("[%s] Simulated %d records", self.name, len(records))
        return records


class SimulatedIndustryHubScraper(BaseScraper):
    """Simulated scraper for industry hub."""

    def scrape(self) -> List[Dict[str, Any]]:
        logger.info("[%s] Simulating scrape from industry hub...", self.name)
        records = []
        for name, domain, industry, size, location, c_name, c_title, c_email in INDUSTRY_HUB_COMPANIES:
            records.append({
                "name": name,
                "website": f"https://{domain}",
                "industry": industry,
                "size": size,
                "location": location,
                "contact_name": c_name,
                "contact_title": c_title,
                "contact_email": c_email,
                "source": self.name,
                "source_reliability": self.reliability,
            })
        time.sleep(0.3)
        logger.info("[%s] Simulated %d records", self.name, len(records))
        return records


class ScraperFactory:
    """Factory to instantiate correct scraper by source name."""

    @staticmethod
    def get_scraper(source_name: str, db: Database = None) -> BaseScraper:
        cfg = next((s for s in CONFIG["sources"] if s["name"] == source_name), None)
        if not cfg:
            raise ValueError(f"Unknown source: {source_name}")

        if source_name == "tech_directory":
            return SimulatedTechDirectoryScraper(cfg, db)
        elif source_name == "crunchbase_sim":
            return SimulatedCrunchbaseScraper(cfg, db)
        elif source_name == "industry_hub":
            return SimulatedIndustryHubScraper(cfg, db)
        else:
            return BaseScraper(cfg, db)

    @staticmethod
    def all_scrapers(db: Database = None) -> List[BaseScraper]:
        return [ScraperFactory.get_scraper(s["name"], db) for s in CONFIG["sources"]]

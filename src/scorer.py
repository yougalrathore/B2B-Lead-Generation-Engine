"""Quality score calculation for leads."""
import logging
from typing import Dict, Any

from src.config import CONFIG

logger = logging.getLogger(__name__)

WEIGHTS = CONFIG["scoring"]["weights"]


class LeadScorer:
    """Calculate 0-100 quality score per lead."""

    @staticmethod
    def completeness_score(company: Dict[str, Any], contact: Dict[str, Any]) -> float:
        """Score based on field completeness (0-100)."""
        company_fields = ["name", "domain", "industry", "size", "location"]
        contact_fields = ["name", "title", "email"]

        company_filled = sum(1 for f in company_fields if company.get(f))
        contact_filled = sum(1 for f in contact_fields if contact.get(f))

        company_pct = (company_filled / len(company_fields)) * 100
        contact_pct = (contact_filled / len(contact_fields)) * 100

        # Weight company data 60%, contact 40%
        return round(company_pct * 0.6 + contact_pct * 0.4, 2)

    @staticmethod
    def source_reliability_score(source_name: str) -> float:
        """Map source name to reliability score."""
        source_map = {
            "crunchbase_sim": 90,
            "tech_directory": 85,
            "industry_hub": 75,
        }
        return source_map.get(source_name, 50)

    @staticmethod
    def email_validity_score(email_result: Dict[str, Any]) -> float:
        """Score from email validation result."""
        return email_result.get("score", 0)

    @staticmethod
    def relevance_score(company: Dict[str, Any]) -> float:
        """Score based on company size and industry relevance."""
        score = 50  # Base
        size = company.get("size", "").lower()

        # Size scoring
        if "enterprise" in size or "1000+" in size or "5000" in size:
            score += 30
        elif "large" in size or "500" in size or "1000" in size:
            score += 20
        elif "medium" in size or "50" in size or "200" in size:
            score += 10
        elif "small" in size or "startup" in size or "1-10" in size:
            score -= 10

        # Industry relevance (tech/SaaS/B2B preferred)
        industry = company.get("industry", "").lower()
        high_value = ["software", "saas", "technology", "fintech", "healthtech", "ai", "cloud", "cybersecurity"]
        medium_value = ["consulting", "marketing", "e-commerce", "logistics"]

        if any(h in industry for h in high_value):
            score += 20
        elif any(m in industry for m in medium_value):
            score += 10

        return min(100, max(0, score))

    @classmethod
    def calculate_total(cls, company: Dict[str, Any], contact: Dict[str, Any],
                        email_result: Dict[str, Any], source_name: str) -> Dict[str, float]:
        """Calculate weighted total score with breakdown."""
        comp = cls.completeness_score(company, contact)
        rel = cls.source_reliability_score(source_name)
        email = cls.email_validity_score(email_result)
        relevance = cls.relevance_score(company)

        total = (
            comp * WEIGHTS["completeness"] +
            rel * WEIGHTS["source_reliability"] +
            email * WEIGHTS["email_validity"] +
            relevance * WEIGHTS["relevance"]
        )

        return {
            "completeness_score": round(comp, 2),
            "source_reliability": round(rel, 2),
            "email_validity": round(email, 2),
            "relevance_score": round(relevance, 2),
            "total_score": round(total, 2),
        }

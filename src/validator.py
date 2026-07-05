"""Email validation: syntax, MX records, disposable detection."""
import re
import socket
import logging
from typing import Dict, Any, Tuple

import dns.resolver
from email_validator import validate_email, EmailNotValidError

from src.config import CONFIG

logger = logging.getLogger(__name__)

DISPOSABLE_DOMAINS = set(CONFIG["validation"]["disposable_domains"])
BLOCKED_TLDS = CONFIG["validation"]["blocked_tlds"]
MX_TIMEOUT = CONFIG["validation"]["mx_timeout"]

EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)


class EmailValidator:
    """Production-grade email validation with DNS checks."""

    @staticmethod
    def validate(email: str) -> Dict[str, Any]:
        """Full validation pipeline. Returns dict with scores and flags."""
        result = {
            "email": email,
            "syntax_valid": False,
            "mx_valid": False,
            "disposable": False,
            "blocked_tld": False,
            "score": 0.0,
            "error": None,
        }

        if not email or not isinstance(email, str):
            result["error"] = "Empty or invalid input"
            return result

        # 1. Syntax check
        if not EMAIL_REGEX.match(email):
            result["error"] = "Syntax mismatch"
            return result
        result["syntax_valid"] = True

        # 2. Disposable domain check
        domain = email.split("@")[1].lower()
        if domain in DISPOSABLE_DOMAINS:
            result["disposable"] = True
            result["error"] = "Disposable domain detected"
            return result

        # 3. Blocked TLD check
        for tld in BLOCKED_TLDS:
            if domain.endswith(tld):
                result["blocked_tld"] = True
                result["error"] = f"Blocked TLD: {tld}"
                return result

        # 4. Enhanced syntax via email-validator library
        try:
            validate_email(email, check_deliverability=False)
        except EmailNotValidError as e:
            result["error"] = f"EmailNotValidError: {e}"
            return result

        # 5. MX Record check
        mx_valid, mx_error = EmailValidator._check_mx(domain)
        result["mx_valid"] = mx_valid
        if not mx_valid:
            result["error"] = mx_error
            # Partial credit for syntax-valid but no MX
            result["score"] = 40.0
            return result

        # All checks passed
        result["score"] = 100.0
        return result

    @staticmethod
    def _check_mx(domain: str) -> Tuple[bool, str]:
        """Check if domain has valid MX records."""
        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout = MX_TIMEOUT
            resolver.lifetime = MX_TIMEOUT
            answers = resolver.resolve(domain, "MX")
            if answers:
                return True, ""
            return False, "No MX records found"
        except dns.resolver.NXDOMAIN:
            return False, "NXDOMAIN"
        except dns.resolver.NoAnswer:
            # Fallback to A record
            try:
                resolver.resolve(domain, "A")
                return True, "A record fallback"
            except Exception:
                return False, "No MX or A records"
        except Exception as e:
            return False, f"DNS error: {e}"

    @staticmethod
    def batch_validate(emails: list) -> list:
        """Validate a list of emails."""
        return [EmailValidator.validate(e) for e in emails if e]

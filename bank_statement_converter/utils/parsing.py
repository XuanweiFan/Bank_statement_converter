"""
Shared parsing helpers for OCR text normalization.
"""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Optional
import re


_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d-%b-%Y",
    "%d %b %Y",
)


def parse_date(value: Optional[str]) -> Optional[date]:
    """Parse a date string into a date object."""
    if not value:
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue

    return None


def parse_amount(value: Optional[str]) -> Optional[Decimal]:
    """Parse a currency string into a Decimal."""
    if not value:
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    upper = cleaned.upper()
    suffix_sign = None
    for token in ("CR", "CREDIT"):
        if upper.endswith(token):
            suffix_sign = 1
            cleaned = cleaned[:-len(token)]
            break

    if suffix_sign is None:
        for token in ("DR", "DEBIT"):
            if upper.endswith(token):
                suffix_sign = -1
                cleaned = cleaned[:-len(token)]
                break

    cleaned = cleaned.replace("$", "").replace(" ", "")

    is_negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        is_negative = True
        cleaned = cleaned[1:-1]
    elif cleaned.startswith("-"):
        is_negative = True
        cleaned = cleaned[1:]
    elif cleaned.startswith("+"):
        cleaned = cleaned[1:]

    if suffix_sign == -1:
        is_negative = True
    elif suffix_sign == 1 and not is_negative:
        is_negative = False

    if "," in cleaned and "." in cleaned and cleaned.rfind(",") > cleaned.rfind("."):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned and "." not in cleaned:
        if re.search(r",\d{2}$", cleaned):
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    else:
        cleaned = cleaned.replace(",", "")

    try:
        amount = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None

    return -amount if is_negative else amount

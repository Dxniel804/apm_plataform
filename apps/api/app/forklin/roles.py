"""What the Central needs translated: its role keys to ours, and an organization name to a slug.

The table is fixed on purpose: a key nobody listed is refused, never turned into a default.
"""

import re
import unicodedata

# Key of the role in the Central -> role of the membership in this product (ADR-020, 2026-10-15).
ROLE_BY_CENTRAL_KEY: dict[str, str] = {"secretaria": "secretaria", "funcionario": "staff"}

DEFAULT_SCHOOL_NAME = "Minha escola"
_SLUG_MAX = 60


def local_role(central_key: str) -> str | None:
    return ROLE_BY_CENTRAL_KEY.get(central_key.strip().lower())


def school_name(raw: str | None) -> str:
    name = " ".join((raw or "").split())[:120]
    return name or DEFAULT_SCHOOL_NAME


def school_slug(name: str, central_org_id: str) -> str:
    """Lower-case ASCII with hyphens (the CHECK of the table); the database makes it unique."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:_SLUG_MAX].strip("-")
    return slug or f"escola-{central_org_id.replace('-', '')[:8]}"

"""Development seed. FAKE data only; refuses to run with ENV=production.

    docker compose run --rm tools python -m app.seed

The demo users get a password (Argon2id): the value of SEED_PASSWORD, or a random one that is
printed ONCE when the users are created (never a value fixed in the repository). It is never logged
and an existing user keeps whatever password it has.

It connects with DATABASE_ADMIN_URL, which in development is a superuser, so it bypasses row level
security by design: the application role cannot create organizations or users (ADR-014). It is safe
to run twice: rows that already exist are left alone.
"""

import os
import secrets
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Connection, create_engine, text

from app.auth.passwords import MIN_LENGTH, hash_password
from app.seed_financial import seed_financial

PRODUCTION_REFUSAL = "refusing to seed: ENV=production. The seed is for development only."
FAKE_EMAIL_DOMAIN = "example.test"

# Each school is a separate customer (ADR-020): its organization is only the account of that one
# school, so there are as many organizations as schools and no person sees two schools by default.
# (slug, name)
ORGANIZATIONS = [
    ("demo-aurora-conta", "Escola Aurora (demo)"),
    ("demo-horizonte-conta", "Escola Horizonte (demo)"),
    ("demo-central-conta", "Escola Central (demo)"),
]
# (slug, name, organization slug)
SCHOOLS = [
    ("demo-aurora", "Escola Aurora (demo)", "demo-aurora-conta"),
    ("demo-horizonte", "Escola Horizonte (demo)", "demo-horizonte-conta"),
    ("demo-central", "Escola Central (demo)", "demo-central-conta"),
]
# (email, full name)
USERS = [
    ("ana.admin@example.test", "Ana Secretária (demo)"),
    ("bruno.diretor@example.test", "Bruno Secretário (demo)"),
    ("carla.tesoureira@example.test", "Carla Secretária (demo)"),
    ("diego.professor@example.test", "Diego Funcionário (demo)"),
    ("fabio.admin@example.test", "Fabio Secretário (demo)"),
    ("gina.tesoureira@example.test", "Gina Secretária (demo)"),
    # Three memberships, one in each school, to try the switch of context in the site: each school
    # invited this person on its own and none of them gives access to another.
    ("helena.multipla@example.test", "Helena Multipla (demo)"),
    # One more teacher in Aurora and one more secretaria in Horizonte, so that every school has a
    # person who submits an expense and a different person who approves it.
    ("paula.professora@example.test", "Paula Funcionária (demo)"),
    ("marcos.tesoureiro@example.test", "Marcos Secretário (demo)"),
]
# (email, organization slug, school slug, role)
MEMBERSHIPS = [
    ("ana.admin@example.test", "demo-horizonte-conta", "demo-horizonte", "secretaria"),
    ("bruno.diretor@example.test", "demo-aurora-conta", "demo-aurora", "secretaria"),
    ("carla.tesoureira@example.test", "demo-aurora-conta", "demo-aurora", "secretaria"),
    ("diego.professor@example.test", "demo-horizonte-conta", "demo-horizonte", "staff"),
    ("fabio.admin@example.test", "demo-central-conta", "demo-central", "secretaria"),
    ("gina.tesoureira@example.test", "demo-central-conta", "demo-central", "secretaria"),
    ("helena.multipla@example.test", "demo-aurora-conta", "demo-aurora", "secretaria"),
    ("helena.multipla@example.test", "demo-horizonte-conta", "demo-horizonte", "staff"),
    ("helena.multipla@example.test", "demo-central-conta", "demo-central", "staff"),
    ("paula.professora@example.test", "demo-aurora-conta", "demo-aurora", "staff"),
    ("marcos.tesoureiro@example.test", "demo-horizonte-conta", "demo-horizonte", "secretaria"),
]


# (name, text, price in cents, limit per order): the products of the demonstration campaign.
DEMO_CAMPAIGN_ITEMS = [
    ("Cachorro-quente", "Pão, salsicha e molho da casa.", 800, 5),
    ("Pamonha", "Doce ou salgada, feita na hora.", 650, None),
    ("Camiseta da festa", "Algodão, do P ao GG.", 4500, 3),
]
DEMO_CAMPAIGN_TITLE = "Festa Junina (demo)"


def seed_campaigns(connection: Connection, count: Callable[[str, int], None]) -> None:
    """One campaign on sale at the first school, so the page of the families has something to show.
    Idempotent: it is skipped when a campaign with that title exists."""
    school = connection.execute(
        text(
            "SELECT s.id, s.organization_id, u.id FROM schools s "
            "JOIN users u ON lower(u.email) = 'carla.tesoureira@example.test' "
            "WHERE s.slug = 'demo-aurora'"
        )
    ).one_or_none()
    if school is None:
        return
    exists = connection.execute(
        text("SELECT 1 FROM campaigns WHERE school_id = :school AND title = :title"),
        {"school": school[0], "title": DEMO_CAMPAIGN_TITLE},
    ).first()
    if exists is not None:
        return
    campaign_id: Any = connection.execute(
        text(
            "INSERT INTO campaigns (organization_id, school_id, created_by_user_id, title, "
            "description) VALUES (:org, :school, :user, :title, :description) RETURNING id"
        ),
        {
            "org": school[1],
            "school": school[0],
            "user": school[2],
            "title": DEMO_CAMPAIGN_TITLE,
            "description": "Barraca de comidas e a camiseta da turma. O que for arrecadado "
            "ajuda a pagar a decoração e as brincadeiras.",
        },
    ).scalar_one()
    count("campaigns", 1)
    for position, (name, description, price, limit) in enumerate(DEMO_CAMPAIGN_ITEMS):
        connection.execute(
            text(
                "INSERT INTO campaign_items (organization_id, school_id, campaign_id, name, "
                "description, price_cents, max_per_order, position) VALUES (:org, :school, "
                ":campaign, :name, :description, :price, :limit, :position)"
            ),
            {
                "org": school[1], "school": school[0], "campaign": campaign_id, "name": name,
                "description": description, "price": price, "limit": limit, "position": position,
            },
        )  # fmt: skip
        count("campaign_items", 1)
    connection.execute(
        text("UPDATE campaigns SET status = 'ACTIVE' WHERE id = :id"), {"id": campaign_id}
    )


@dataclass
class SeedSummary:
    """How many rows this run created, per table."""

    created: dict[str, int] = field(default_factory=dict)


def seed(connection: Connection, password: str | None = None) -> SeedSummary:
    """Insert the fake data. Idempotent: existing rows (by slug, e-mail or membership) are kept.

    With a `password`, new users can log in with it (each gets its own Argon2id hash); without
    one they have no password and cannot log in until they are given one.
    """
    summary = SeedSummary()

    def count(table: str, rows: int) -> None:
        summary.created[table] = summary.created.get(table, 0) + rows

    for slug, name in ORGANIZATIONS:
        result = connection.execute(
            text(
                "INSERT INTO organizations (name, slug) VALUES (:name, :slug) "
                "ON CONFLICT DO NOTHING"
            ),
            {"name": name, "slug": slug},
        )
        count("organizations", result.rowcount)
    for slug, name, org_slug in SCHOOLS:
        result = connection.execute(
            text(
                "INSERT INTO schools (organization_id, name, slug) "
                "SELECT id, :name, :slug FROM organizations WHERE slug = :org_slug "
                "ON CONFLICT DO NOTHING"
            ),
            {"name": name, "slug": slug, "org_slug": org_slug},
        )
        count("schools", result.rowcount)
    for email, full_name in USERS:
        result = connection.execute(
            text(
                "INSERT INTO users (email, full_name, password_hash) "
                "VALUES (:email, :full_name, :password_hash) ON CONFLICT DO NOTHING"
            ),
            {
                "email": email,
                "full_name": full_name,
                "password_hash": None if password is None else hash_password(password),
            },
        )
        count("users", result.rowcount)
    for email, org_slug, school_slug, role in MEMBERSHIPS:
        result = connection.execute(
            text(
                "INSERT INTO memberships (user_id, organization_id, school_id, role, status) "
                "SELECT u.id, o.id, s.id, :role, 'active' "
                "FROM users u JOIN organizations o ON o.slug = :org_slug "
                "JOIN schools s ON s.slug = :school_slug AND s.organization_id = o.id "
                "WHERE lower(u.email) = lower(:email) "
                "ON CONFLICT DO NOTHING"
            ),
            {"email": email, "org_slug": org_slug, "school_slug": school_slug, "role": role},
        )
        count("memberships", result.rowcount)
    seed_financial(connection, count)  # categories and demonstration movements (ADR-015)
    seed_campaigns(connection, count)  # a campaign on sale at the first school (0013)
    return summary


def main() -> int:
    # Checked before anything else, including before the settings are loaded and before any
    # connection is opened.
    if os.environ.get("ENV", "").strip().lower() == "production":
        print(PRODUCTION_REFUSAL, file=sys.stderr)
        return 1
    from app.core.config import get_admin_settings

    settings = get_admin_settings()
    if settings.is_production:
        print(PRODUCTION_REFUSAL, file=sys.stderr)
        return 1
    chosen = os.environ.get("SEED_PASSWORD")
    if chosen is not None and len(chosen) < MIN_LENGTH:
        print(
            f"refusing to seed: SEED_PASSWORD must have at least {MIN_LENGTH} characters",
            file=sys.stderr,
        )
        return 1
    generated = chosen is None
    password = secrets.token_urlsafe(18) if chosen is None else chosen
    engine = create_engine(settings.database_admin_url.get_secret_value())
    try:
        with engine.begin() as connection:
            bypasses_rls: Any = connection.execute(
                text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
            ).scalar_one()
            if not bypasses_rls:
                print(
                    "refusing to seed: the admin role must be able to bypass row level security "
                    "(a development superuser); the application role cannot create tenants.",
                    file=sys.stderr,
                )
                return 1
            summary = seed(connection, password)
    finally:
        engine.dispose()
    for table, created in summary.created.items():
        print(f"{table}: {created} created")
    if generated and summary.created.get("users"):
        # Shown once, and only when users were just created with it; SEED_PASSWORD is never echoed.
        print(f"password of the demo users (shown once): {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

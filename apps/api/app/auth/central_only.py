"""With the Forklin Central ON, people exist only there (docs/adr-forklin-sso.md, sections 7 and 8).

* The APM no longer registers staff: every route that creates, invites, suspends or reactivates a
  person answers 404 (`staff_registration_closed`), and an invitation sent before the switch can no
  longer be accepted.
* A person who comes from the Central (`users.central_user_id`) enters only through it: the
  password never opens a session, and the recovery flow neither makes nor spends a reset for them.

Everything is behind `FORKLIN_CORE_ENABLED`; with it off (the default) none of this exists.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.auth.deps import Settings
from app.auth.identity import is_central_linked
from app.core.config import ApiSettings
from app.core.errors import ProblemError


def staff_registration_closed(settings: Settings) -> None:
    """Dependency of the routes that register or manage staff: 404 while the Central is ON."""
    if settings.forklin_core_enabled:
        raise ProblemError(404, "not_found", "Not found")


def password_is_off_for(
    db: Session,
    settings: ApiSettings,
    *,
    user_id: UUID | None = None,
    email: str | None = None,
) -> bool:
    """True when this person must not use (or get) a local password. Always False with the Central
    off, and no query is made then."""
    if not settings.forklin_core_enabled:
        return False
    return is_central_linked(db, user_id=user_id, email=email)

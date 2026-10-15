"""Permissions: a map role -> permissions in CODE (ADR-016), and the markers every route must carry.

Every route declares exactly one of:
  require(Permission.X)  an authenticated user whose role holds that permission
  authenticated()        any authenticated user (the route is about the user themself)
  public()               no session needed: it must be listed in PUBLIC_ROUTES, with the reason
A test walks every registered route and fails when one has none, or has two, or is public without
being in the list.
"""

from enum import StrEnum


class Permission(StrEnum):
    # Access management (this task)
    INVITATIONS_CREATE = "invitations:create"
    MEMBERSHIPS_MANAGE = "memberships:manage"
    # Organization and school data
    ORGANIZATION_UPDATE = "organization:update"
    SCHOOL_UPDATE = "school:update"
    # Money (ADR-015/016): the routes arrive with the financial tasks, the permissions are
    # decided now
    CONTRIBUTIONS_RECORD_CASH = "contributions:record_cash"
    EXPENSES_SUBMIT = "expenses:submit"
    EXPENSES_READ_OWN = "expenses:read_own"
    EXPENSES_READ_ALL = "expenses:read_all"
    EXPENSES_APPROVE = "expenses:approve"
    REIMBURSEMENTS_REGISTER = "reimbursements:register"
    REFUNDS_REGISTER = "refunds:register"
    MONTHS_CLOSE = "months:close"
    MONTHS_REOPEN = "months:reopen"
    STATEMENT_READ = "statement:read"
    REPORTS_READ = "reports:read"
    REPORTS_READ_AGGREGATE = "reports:read_aggregate"
    # Requests of the staff to the management (migration 0012): not money.
    REQUESTS_SUBMIT = "requests:submit"
    REQUESTS_READ_OWN = "requests:read_own"
    REQUESTS_READ_ALL = "requests:read_all"
    REQUESTS_MANAGE = "requests:manage"
    # The campaigns the management sells to the families (migration 0013).
    CAMPAIGNS_MANAGE = "campaigns:manage"
    # The settings the management of a school edits: the amounts the family is offered, the goals of
    # the month, the public link and its poster (migration 0015).
    SCHOOL_SETTINGS_MANAGE = "school_settings:manage"
    # The bank accounts of a school and the statements compared with the ledger (migration 0017).
    RECONCILIATION_MANAGE = "reconciliation:manage"


ALL_PERMISSIONS = frozenset(Permission)

# Every role belongs to ONE school (ADR-020): there is no role that spans schools.
ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    # Everything in the school, including reopening a closed month (ADR-015, ADR-020): the
    # treasurer who closes it cannot reopen it.
    "school_admin": ALL_PERMISSIONS,
    "treasurer": frozenset(
        {
            Permission.CONTRIBUTIONS_RECORD_CASH,
            Permission.EXPENSES_READ_ALL,
            Permission.EXPENSES_APPROVE,
            Permission.REIMBURSEMENTS_REGISTER,
            Permission.REFUNDS_REGISTER,
            Permission.MONTHS_CLOSE,
            Permission.STATEMENT_READ,
            Permission.REPORTS_READ,
            # The management answers the requests of the staff.
            Permission.REQUESTS_READ_ALL,
            Permission.REQUESTS_MANAGE,
            # The management writes the campaigns and their products.
            Permission.CAMPAIGNS_MANAGE,
            Permission.SCHOOL_SETTINGS_MANAGE,
            Permission.RECONCILIATION_MANAGE,
        }
    ),
    # Staff (funcionario): submit and see their OWN expenses, and ask the management for things.
    "staff": frozenset(
        {
            Permission.EXPENSES_SUBMIT,
            Permission.EXPENSES_READ_OWN,
            Permission.REQUESTS_SUBMIT,
            Permission.REQUESTS_READ_OWN,
        }
    ),
    # Aggregate reading only, no personal data of guardians.
    "viewer": frozenset({Permission.REPORTS_READ_AGGREGATE}),
}

# Roles an inviter may grant, by the inviter's own role (always into the inviter's own school).
INVITABLE_ROLES: dict[str, frozenset[str]] = {
    "school_admin": frozenset({"school_admin", "treasurer", "staff", "viewer"}),
}


def permissions_for(role: str | None) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role or "", frozenset())


class PermissionRequirement:
    """Marker + dependency: the route needs this permission. Built by `require()`."""

    def __init__(self, permission: Permission) -> None:
        self.permission = permission


class AuthenticatedMarker:
    """Marker: the route needs a session but no particular permission."""


class PublicMarker:
    """Marker: the route needs no session."""


# (method, path) -> why it is public. The walk of the routes compares this with reality.
PUBLIC_ROUTES: dict[tuple[str, str], str] = {
    ("GET", "/api/health"): "liveness probe",
    ("GET", "/api/health/ready"): "readiness probe",
    ("POST", "/api/v1/auth/login"): "proves who the person is; rate limited and Origin checked",
    ("POST", "/api/v1/auth/logout"): "idempotent; verifies CSRF when a session is presented",
    ("POST", "/api/v1/invitations/accept"): "the invitation token is the credential; rate limited",
    # The public contribution flow (ADR-010, ADR-018): the slug and the receipt token are the scope.
    ("GET", "/api/v1/public/schools/{slug}"): "the public page of a school",
    ("POST", "/api/v1/public/schools/{slug}/contributions"): "a family starts a contribution; "
    "revalidated, rate limited per address, Origin checked, Idempotency-Key",
    ("GET", "/api/v1/public/schools/{slug}/contributions/{token}/charge"): "the receipt token "
    "is the credential; unknown tokens count against the address",
    ("POST", "/api/v1/public/schools/{slug}/contributions/{token}/charges"): "the receipt "
    "token is the credential; a new charge only when the previous one expired",
    ("GET", "/api/v1/public/schools/{slug}/contributions/{token}/receipt"): "the receipt token "
    "is the credential; 200 only when PAID",
    # The campaigns on sale (migration 0013): the page, the cart and the pictures of a school.
    ("GET", "/api/v1/public/schools/{slug}/campaigns"): "the campaigns on sale at a school",
    ("GET", "/api/v1/public/schools/{slug}/campaigns/{campaign_id}"): "one campaign on sale, "
    "with its products",
    ("GET", "/api/v1/public/schools/{slug}/campaigns/{campaign_id}/cover"): "the cover of a "
    "campaign on sale",
    ("GET", "/api/v1/public/schools/{slug}/campaigns/{campaign_id}/items/{item_id}/image"): "the "
    "picture of a product of a campaign on sale",
    ("POST", "/api/v1/public/schools/{slug}/campaigns/{campaign_id}/orders"): "a family orders "
    "products; the total is recomputed from the prices of the server, rate limited per address, "
    "Origin checked, Idempotency-Key",
    ("POST", "/api/v1/webhooks/pix/sandbox"): "authenticated by X-Webhook-Secret (a hash is "
    "compared); no browser Origin; idempotent by event id; the provider is asked again",
    ("POST", "/api/v1/webhooks/pix/bb"): "authenticated by X-Webhook-Secret (a hash is compared); "
    "no browser Origin; the real provider arrives in M2",
    ("POST", "/api/v1/dev/sandbox/pix/{txid}/pay"): "development and tests only: 404 elsewhere",
}
# Documentation routes FastAPI registers itself (not APIRoute objects with dependencies).
PUBLIC_FRAMEWORK_PATHS = frozenset({"/api/openapi.json", "/api/docs", "/api/redoc"})

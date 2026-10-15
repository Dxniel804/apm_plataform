# Staff requests (Solicitações)

Code: `apps/api/app/staff_requests/` (router, service, repository, schemas), migration `0012_staff_requests.py`, models in `app/models/staff_requests.py`. The photos use the same store and the same upload rules as the receipts of an expense ([expenses.md](expenses.md)). It is **not money**: nothing here touches the ledger.

A *funcionário* opens a request to the management (a category, a title, a description and photos taken on the spot or chosen from the gallery); the *secretaria* sees them all, filters by status and category, marks one as in progress and as resolved, with a note the author reads.

## Who may do what

| Permission | Roles | What it allows |
| --- | --- | --- |
| `requests:submit` | `staff` | open a request, attach photos to **your own** open request, cancel your own |
| `requests:read_own` | `staff` | read the requests you wrote |
| `requests:read_all` | `secretaria` | read every request of the school |
| `requests:manage` | `secretaria` | start and resolve any request |

Somebody else's request is the same `404 not_found` as one that never existed, for whoever reads only their own.

## Routes

All under `/api/v1/schools/{school_id}` (the school is checked against the session, like everywhere).

| Method and path | Permission | What it does |
| --- | --- | --- |
| `POST /requests` | `requests:submit` | Opens a request (`category`, `title`, optional `description`). Always OPEN, the author is the person of the session |
| `GET /requests` | `requests:read_own` or `requests:read_all` | `{items, next_cursor}`, newest first. `?status=`, `?category=`, `?period=YYYY-MM` (month of the creation, in the school's time zone), `?cursor=`, `?limit=` (1 to 100) |
| `GET /requests/{id}` | same | The request with its photos |
| `POST /requests/{id}/attachments` | `requests:submit` | Multipart `file`: a PNG, JPEG or WebP photo (the type comes from the first bytes). Author only, only while OPEN or IN_PROGRESS, at most 6 photos, the same file once |
| `GET /requests/{id}/attachments/{attachment_id}` | read | Downloads the photo (`Content-Disposition: attachment`, `nosniff`, `Cache-Control: private, no-store`) |
| `POST /requests/{id}/start` | `requests:manage` | OPEN to IN_PROGRESS |
| `POST /requests/{id}/resolve` | `requests:manage` | OPEN or IN_PROGRESS to RESOLVED. Body optional: `note` (1 to 1000 characters) |
| `POST /requests/{id}/cancel` | `requests:submit` | The author withdraws it, while OPEN or IN_PROGRESS |

Categories (fixed for now): `SUPPLIES`, `MAINTENANCE`, `EVENT`, `FINANCE`, `OTHER`; the site translates them. Statuses: `OPEN`, `IN_PROGRESS`, `RESOLVED` (final), `CANCELLED` (final).

## Errors

`application/problem+json` as in [auth.md](auth.md#errors). Besides the usual `401`, `403 permission_denied`, `404 not_found` and `422 validation_error`:

| Status | `code` | When |
| --- | --- | --- |
| 403 | `author_only` | someone who can see the request, but did not write it, tries to attach a photo or cancel it |
| 409 | `invalid_state` | the action does not apply in the current state (`detail` names it) |
| 409 | `attachments_closed`, `attachment_limit`, `attachment_duplicate` | photos |
| 411, 413, 415 | `length_required`, `payload_too_large`, `attachment_type_not_allowed` | the upload (a PDF is `415`: photos only) |

## In the database

`staff_requests` and `staff_request_attachments` follow the checklist of [tenancy.md](tenancy.md) and [financial-model.md](financial-model.md): scope and composite foreign keys, every unique index with `school_id`, `*_user_id` guarded by `assert_active_member`, write policies that also check the school belongs to the organization, grants by column and no `DELETE`, immutability and final states by trigger (the inventory is in [financial-model.md](financial-model.md#trigger-inventory)), and an audit trail that never copies free text. The service adds one event per action (`request.created`, `.attachment_added`, `.started`, `.resolved`, `.cancelled`) with ids and states only.

## Not done, on purpose

- Editing a request after it was opened (open a new one, or cancel); custom categories chosen by the management; notifying the author by e-mail; deleting anything.

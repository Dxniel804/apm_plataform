"""What the database itself guarantees about the requests, whatever the application does: the
grants by column, the states, what never changes, who can be named, and that nothing is deleted."""

import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.dbsupport import transaction
from tests.expenses.support import Scene
from tests.staff_requests.support import manager, opened, with_photo

REQUEST_COLUMNS = [
    "id",
    "organization_id",
    "school_id",
    "author_user_id",
    "category",
    "title",
    "description",
    "status",
    "started_at",
    "started_by_user_id",
    "resolved_at",
    "resolved_by_user_id",
    "resolution_note",
    "created_at",
    "updated_at",
]
ATTACHMENT_COLUMNS = [
    "id",
    "organization_id",
    "school_id",
    "request_id",
    "storage_key",
    "file_name",
    "content_type",
    "size_bytes",
    "sha256",
    "uploaded_by_user_id",
    "created_at",
    "updated_at",
]
INSERTABLE = {
    "staff_requests": {
        "organization_id",
        "school_id",
        "author_user_id",
        "category",
        "title",
        "description",
    },
    "staff_request_attachments": {
        "organization_id",
        "school_id",
        "request_id",
        "storage_key",
        "file_name",
        "content_type",
        "size_bytes",
        "sha256",
        "uploaded_by_user_id",
    },
}
UPDATABLE = {
    "staff_requests": {
        "status",
        "started_at",
        "started_by_user_id",
        "resolved_at",
        "resolved_by_user_id",
        "resolution_note",
        "updated_at",
    },
    "staff_request_attachments": set(),
}
COLUMNS = {"staff_requests": REQUEST_COLUMNS, "staff_request_attachments": ATTACHMENT_COLUMNS}


def _privileges(engine: Engine, table: str, privilege: str) -> set[str]:
    with engine.connect() as connection:
        return {
            column
            for column in COLUMNS[table]
            if connection.execute(
                text("SELECT has_column_privilege('apm_app', :t, :c, :p)"),
                {"t": table, "c": column, "p": privilege},
            ).scalar_one()
        }


@pytest.mark.parametrize("table", ["staff_requests", "staff_request_attachments"])
def test_the_application_role_writes_by_column_and_never_deletes(
    admin_engine: Engine, table: str
) -> None:
    assert _privileges(admin_engine, table, "SELECT") == set(COLUMNS[table])
    assert _privileges(admin_engine, table, "INSERT") == INSERTABLE[table]
    assert _privileges(admin_engine, table, "UPDATE") == UPDATABLE[table]
    with admin_engine.connect() as connection:
        for privilege in ("DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            allowed: Any = connection.execute(
                text("SELECT has_table_privilege('apm_app', :t, :p)"),
                {"t": table, "p": privilege},
            ).scalar_one()
            assert allowed is False, privilege


def _refused(engine: Engine, sql: str, params: dict[str, Any], *needles: str) -> None:
    """Run `sql` as the admin (a superuser in development, so row level security does not get in
    the way: only the triggers and the constraints can stop it) and expect the database to refuse
    with one of the texts."""
    with transaction(engine) as connection:
        try:
            connection.execute(text(sql), params)
        except DBAPIError as error:
            message = str(error.orig).lower()
            assert any(needle in message for needle in needles), message
        else:
            raise AssertionError("the database accepted it")


def test_a_resolved_request_changes_in_no_column(scene: Scene, admin_engine: Engine) -> None:
    author = scene.person("staff", label="author")
    request = opened(author)
    manager(scene).post(f"/requests/{request['id']}/resolve", {"note": "Feito"})

    for sql in (
        "UPDATE staff_requests SET status = 'OPEN' WHERE id = :id",
        "UPDATE staff_requests SET resolution_note = 'outra' WHERE id = :id",
        "UPDATE staff_requests SET status = 'CANCELLED' WHERE id = :id",
    ):
        _refused(admin_engine, sql, {"id": request["id"]}, "final", "can never")


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("title", "'Outro titulo'"),
        ("description", "'Outra descricao'"),
        ("category", "'EVENT'"),
        ("author_user_id", "'00000000-0000-4000-8000-000000000001'"),
        ("school_id", "'00000000-0000-4000-8000-000000000001'"),
        ("created_at", "now() - interval '1 day'"),
    ],
)
def test_what_the_author_wrote_never_changes(
    scene: Scene, admin_engine: Engine, column: str, value: str
) -> None:
    request = opened(scene.person("staff", label="author"))

    _refused(
        admin_engine,
        f"UPDATE staff_requests SET {column} = {value} WHERE id = :id",  # noqa: S608
        {"id": request["id"]},
        "can never change",
        "foreign key",
        "row-level security",
        "invalid user reference",
    )


def test_the_edges_of_the_states_are_closed_by_the_database(
    scene: Scene, admin_engine: Engine
) -> None:
    request = opened(scene.person("staff", label="author"))
    manager(scene).post(f"/requests/{request['id']}/start")

    # IN_PROGRESS never goes back to OPEN, whatever the application does
    _refused(
        admin_engine,
        "UPDATE staff_requests SET status = 'OPEN' WHERE id = :id",
        {"id": request["id"]},
        "cannot go from",
    )


def test_who_started_and_who_resolved_are_written_once(scene: Scene, admin_engine: Engine) -> None:
    request = opened(scene.person("staff", label="author"))
    gestao = manager(scene)
    other = manager(scene, "outra-gestao")
    gestao.post(f"/requests/{request['id']}/start")

    _refused(
        admin_engine,
        "UPDATE staff_requests SET started_by_user_id = :u WHERE id = :id",
        {"id": request["id"], "u": other.user.id},
        "was already set",
    )


def test_only_a_member_of_the_school_can_be_named(scene: Scene, admin_engine: Engine) -> None:
    request = opened(scene.person("staff", label="author"))
    stranger = scene.person("staff", org="b", label="stranger")  # a person of ANOTHER school

    for who in (stranger.user.id, uuid.uuid4()):  # an existing person and a made-up one: the same
        _refused(
            admin_engine,
            "UPDATE staff_requests SET status = 'IN_PROGRESS', started_at = now(), "
            "started_by_user_id = :u WHERE id = :id",
            {"id": request["id"], "u": who},
            "invalid user reference",
        )


def test_a_request_is_never_deleted(scene: Scene, admin_engine: Engine) -> None:
    request = opened(scene.person("staff", label="author"))

    _refused(
        admin_engine,
        "DELETE FROM staff_requests WHERE id = :id",
        {"id": request["id"]},
        "can never",
        "delete",
    )
    _refused(admin_engine, "TRUNCATE staff_requests", {}, "can never", "truncate")


def test_a_photo_is_insert_only_and_only_on_an_open_request(
    scene: Scene, admin_engine: Engine
) -> None:
    author = scene.person("staff", label="author")
    request = opened(author)
    photo = with_photo(author, request["id"])
    manager(scene).post(f"/requests/{request['id']}/resolve", {})

    _refused(
        admin_engine,
        "UPDATE staff_request_attachments SET file_name = 'x.png' WHERE id = :id",
        {"id": photo["id"]},
        "can never be updated",
        "update",
    )
    _refused(
        admin_engine,
        "INSERT INTO staff_request_attachments (organization_id, school_id, request_id, "
        "storage_key, file_name, content_type, size_bytes, sha256, uploaded_by_user_id) "
        "SELECT organization_id, school_id, id, 'k', 'a.png', 'image/png', 10, repeat('a', 64), "
        "author_user_id FROM staff_requests WHERE id = :id",
        {"id": request["id"]},
        "open staff request",
    )


@pytest.mark.parametrize(
    "content_type", ["application/pdf", "image/svg+xml", "text/html", "image/gif"]
)
def test_the_database_only_takes_photo_types(
    scene: Scene, admin_engine: Engine, content_type: str
) -> None:
    request = opened(scene.person("staff", label="author"))

    _refused(
        admin_engine,
        "INSERT INTO staff_request_attachments (organization_id, school_id, request_id, "
        "storage_key, file_name, content_type, size_bytes, sha256, uploaded_by_user_id) "
        "SELECT organization_id, school_id, id, 'k', 'a.bin', :t, 10, repeat('b', 64), "
        "author_user_id FROM staff_requests WHERE id = :id",
        {"id": request["id"], "t": content_type},
        "content_type_image",
    )

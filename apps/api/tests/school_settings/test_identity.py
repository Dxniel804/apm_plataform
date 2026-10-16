# ruff: noqa: E501  (SQL and long assertions)
"""The name and the address of a school (migration 0024): the name changes freely; the address changes twice
freely and then only every 15 days; every address ever used stays reserved to its school and keeps
opening it (families pay through it)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, text

from tests.expenses.support import Scene
from tests.financial.support import create_account


def _original(engine: Engine, school: uuid.UUID) -> str:
    with engine.connect() as conn:
        return str(
            conn.execute(text("SELECT slug FROM schools WHERE id = :s"), {"s": school}).scalar_one()
        )


@pytest.fixture
def identity_scene(scene: Scene, admin_engine: Engine) -> Iterator[Scene]:
    """The shared test schools outlast a test: the address, the counters and the history come back."""
    school = scene.world.school_a1
    original = _original(admin_engine, school)
    yield scene
    with admin_engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(
            text("DELETE FROM school_slug_history WHERE school_id = :s AND slug <> :o"),
            {"s": school, "o": original},
        )
        conn.execute(
            text(
                "UPDATE schools SET slug = :o, slug_changes = 0, slug_changed_at = NULL, name = 'School A1' WHERE id = :s"
            ),
            {"s": school, "o": original},
        )
        conn.execute(
            text(
                "DELETE FROM payment_accounts WHERE school_id = :s AND external_account_id LIKE 'ident-%'"
            ),
            {"s": school},
        )


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def _patch(person: Any, **body: Any) -> Any:
    return person.patch("/identity", body)


def test_the_identity_comes_with_what_is_left_of_the_changes(identity_scene: Scene) -> None:
    body = identity_scene.person("secretaria").get("/identity").json()
    assert body["free_changes_left"] == 2 and body["slug_changes"] == 0
    assert body["slug_locked_until"] is None
    assert body["url"].endswith(f"/escola/{body['slug']}")
    assert body["previous_slugs"] == []


def test_the_name_changes_freely_and_is_audited(
    identity_scene: Scene, admin_engine: Engine
) -> None:
    gestao = identity_scene.person("secretaria")
    for name in ("Escola Estadual Ipê", "Escola Ipê Roxo"):
        assert _patch(gestao, name=f"  {name}  ").json()["name"] == name
    with admin_engine.connect() as conn:
        seen: Any = conn.execute(
            text(
                "SELECT count(*) FROM audit_logs WHERE school_id = :s AND action = 'schools.renamed'"
            ),
            {"s": identity_scene.world.school_a1},
        ).scalar_one()
    assert seen == 2


def test_two_changes_of_the_address_are_free_and_the_third_waits_fifteen_days(
    identity_scene: Scene, admin_engine: Engine
) -> None:
    gestao = identity_scene.person("secretaria")
    first, second, third = (f"escola-{_suffix()}" for _ in range(3))
    assert _patch(gestao, slug=first).json()["slug"] == first
    body = _patch(gestao, slug=second).json()
    assert body["slug"] == second and body["free_changes_left"] == 0 and body["slug_changes"] == 2
    assert body["slug_locked_until"] is not None
    assert body["previous_slugs"][:1] == [first]

    locked = _patch(gestao, slug=third)
    assert locked.status_code == 409 and locked.json()["code"] == "slug_change_locked"

    # 14 days later it is still locked, 16 days later it opens (the clock is the stored moment)
    for days, expected in ((14, 409), (16, 200)):
        with admin_engine.begin() as conn:
            conn.execute(text("SET LOCAL session_replication_role = replica"))
            conn.execute(
                text("UPDATE schools SET slug_changed_at = :at WHERE id = :s"),
                {
                    "at": datetime.now(UTC) - timedelta(days=days),
                    "s": identity_scene.world.school_a1,
                },
            )
        assert _patch(gestao, slug=third).status_code == expected
    # and after the third the wait starts again
    again = _patch(gestao, slug=f"escola-{_suffix()}")
    assert again.status_code == 409 and again.json()["code"] == "slug_change_locked"


def test_the_database_decides_even_when_the_service_is_skipped(
    identity_scene: Scene, admin_engine: Engine
) -> None:
    """The counters are the trigger's: the application role cannot even write them."""
    with admin_engine.connect() as conn:
        for column in ("slug_changes", "slug_changed_at"):
            can: Any = conn.execute(
                text("SELECT has_column_privilege('apm_app', 'schools', :c, 'UPDATE')"),
                {"c": column},
            ).scalar_one()
            assert can is False, column
        assert conn.execute(
            text("SELECT has_column_privilege('apm_app', 'schools', 'slug', 'UPDATE')")
        ).scalar_one()
    with admin_engine.begin() as conn:
        conn.execute(
            text("SET LOCAL session_replication_role = replica")
        )  # forging the state: no trigger
        conn.execute(
            text("UPDATE schools SET slug_changes = 2, slug_changed_at = now() WHERE id = :s"),
            {"s": identity_scene.world.school_a1},
        )
    gestao = identity_scene.person("secretaria")
    # the service says it first...
    assert _patch(gestao, slug=f"escola-{_suffix()}").status_code == 409


def test_reserved_words_and_malformed_addresses_are_refused(identity_scene: Scene) -> None:
    gestao = identity_scene.person("secretaria")
    for word in ("admin", "api", "login", "painel", "forklin"):
        refused = _patch(gestao, slug=word)
        assert refused.status_code == 422 and refused.json()["code"] == "slug_reserved", word
    for bad in ("ab", "Escola Nova!", "-escola", "escola--x", "a" * 41, "escola_nova"):
        assert _patch(gestao, slug=bad).status_code == 422, bad
    # none of those used up a free change
    assert gestao.get("/identity").json()["free_changes_left"] == 2


def test_an_address_of_another_school_is_taken_and_so_is_one_it_used_to_have(
    identity_scene: Scene, admin_engine: Engine
) -> None:
    gestao = identity_scene.person("secretaria")
    other = identity_scene.world.school_b1
    with admin_engine.connect() as conn:
        theirs: Any = conn.execute(
            text("SELECT slug FROM schools WHERE id = :s"), {"s": other}
        ).scalar_one()
    taken = _patch(gestao, slug=theirs)
    assert taken.status_code == 409 and taken.json()["code"] == "slug_taken"

    # the other school moves away from its address: it is STILL reserved to it
    with admin_engine.begin() as conn:
        conn.execute(
            text("UPDATE schools SET slug = :n WHERE id = :s"),
            {"n": f"moved-{_suffix()}", "s": other},
        )
    try:
        still = _patch(gestao, slug=theirs)
        assert still.status_code == 409 and still.json()["code"] == "slug_taken"
    finally:
        with admin_engine.begin() as conn:
            conn.execute(text("SET LOCAL session_replication_role = replica"))
            conn.execute(
                text("DELETE FROM school_slug_history WHERE school_id = :s AND slug <> :o"),
                {"s": other, "o": theirs},
            )
            conn.execute(
                text(
                    "UPDATE schools SET slug = :o, slug_changes = 0, slug_changed_at = NULL WHERE id = :s"
                ),
                {"s": other, "o": theirs},
            )
    assert gestao.get("/identity").json()["free_changes_left"] == 2


def test_a_school_may_go_back_to_an_address_it_had(identity_scene: Scene) -> None:
    gestao = identity_scene.person("secretaria")
    original = gestao.get("/identity").json()["slug"]
    new = f"escola-{_suffix()}"
    assert _patch(gestao, slug=new).status_code == 200
    back = _patch(gestao, slug=original)
    assert back.status_code == 200 and back.json()["slug"] == original


def test_an_old_address_keeps_opening_the_school_in_the_public_flow(
    identity_scene: Scene, admin_engine: Engine, apis: Any
) -> None:
    world = identity_scene.world
    with admin_engine.begin() as conn:
        org: Any = conn.execute(
            text("SELECT organization_id FROM schools WHERE id = :s"), {"s": world.school_a1}
        ).scalar_one()
        create_account(conn, org, world.school_a1)
        conn.execute(
            text(
                "UPDATE payment_accounts SET external_account_id = 'ident-' || external_account_id WHERE school_id = :s"
            ),
            {"s": world.school_a1},
        )
    gestao = identity_scene.person("secretaria")
    before = gestao.get("/identity").json()
    assert before["link_active"] is True
    new = f"escola-{_suffix()}"
    changed = _patch(gestao, slug=new)
    assert changed.status_code == 200, changed.text

    public = apis.make()
    by_new = public.get(f"/api/v1/public/schools/{new}")
    by_old = public.get(f"/api/v1/public/schools/{before['slug']}")
    assert by_new.status_code == 200 and by_old.status_code == 200
    # the same school, announced by its CURRENT address, so the site can redirect
    assert by_new.json()["slug"] == new and by_old.json()["slug"] == new
    assert public.get("/api/v1/public/schools/nunca-existiu-nenhuma-escola").status_code == 404


def test_without_a_receiving_account_the_link_says_it_is_not_active_yet(
    identity_scene: Scene,
) -> None:
    gestao = identity_scene.person("secretaria")
    body = _patch(gestao, slug=f"escola-{_suffix()}").json()
    assert body["link_active"] is False  # the page opens only with an active account


def test_only_the_secretaria_of_that_school_may(identity_scene: Scene) -> None:
    employee = identity_scene.person("staff")
    assert employee.get("/identity").status_code == 403
    assert _patch(employee, name="Outra Escola").status_code == 403
    assert _patch(identity_scene.person("secretaria"), name=None).status_code in (200, 422)

"""The life of a request: opened by the staff, answered by the management."""

from typing import Any

import pytest
from sqlalchemy import text

from tests.expenses.support import Scene
from tests.staff_requests.support import manager, opened


def ids(response: Any) -> list[str]:
    return [item["id"] for item in response.json()["items"]]


def test_a_request_is_opened_by_the_person_of_the_session_and_born_open(scene: Scene) -> None:
    author = scene.person("staff", label="author")

    response = author.post(
        "/requests", {"category": "MAINTENANCE", "title": "  Torneira pingando  "}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "OPEN" and body["category"] == "MAINTENANCE"
    assert body["title"] == "Torneira pingando"  # trimmed
    assert body["description"] is None
    assert body["author_user_id"] == str(author.user.id)
    assert body["attachments"] == [] and body["attachments_count"] == 0
    assert body["started_at"] is None and body["resolved_at"] is None
    assert body["resolution_note"] is None


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"title": "Sem categoria"},
        {"category": "SUPPLIES"},
        {"category": "NOPE", "title": "x"},
        {"category": "supplies", "title": "x"},
        {"category": "SUPPLIES", "title": ""},
        {"category": "SUPPLIES", "title": "   "},
        {"category": "SUPPLIES", "title": "x" * 121},
        {"category": "SUPPLIES", "title": "x", "description": ""},
        {"category": "SUPPLIES", "title": "x", "description": "d" * 2001},
        {"category": "SUPPLIES", "title": "x\x00y"},
        # nothing about who or where comes from the body
        {
            "category": "SUPPLIES",
            "title": "x",
            "author_user_id": "00000000-0000-4000-8000-000000000001",
        },
        {"category": "SUPPLIES", "title": "x", "status": "RESOLVED"},
        {"category": "SUPPLIES", "title": "x", "school_id": "00000000-0000-4000-8000-000000000001"},
    ],
)
def test_a_malformed_request_is_a_422_and_creates_nothing(
    scene: Scene, body: dict[str, Any]
) -> None:
    author = scene.person("staff", label="author")

    response = author.post("/requests", body)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"
    assert author.get("/requests").json()["items"] == []


def test_the_author_reads_only_their_own_and_the_management_reads_all(scene: Scene) -> None:
    ana = scene.person("staff", label="ana")
    beto = scene.person("staff", label="beto")
    gestao = manager(scene)
    mine, theirs = opened(ana), opened(beto)

    assert ids(ana.get("/requests")) == [mine["id"]]
    assert ids(beto.get("/requests")) == [theirs["id"]]
    assert {mine["id"], theirs["id"]} <= set(ids(gestao.get("/requests", params={"limit": 100})))
    assert ana.get(f"/requests/{theirs['id']}").status_code == 404
    assert gestao.get(f"/requests/{theirs['id']}").status_code == 200


def test_the_list_is_newest_first_filters_and_pages(scene: Scene) -> None:
    # `ana` reads only her own requests, so this list is hers alone whatever the school holds.
    ana = scene.person("staff", label="ana")
    gestao = manager(scene)
    made = [
        opened(ana, title=f"Pedido {i}", category="EVENT" if i % 2 else "OTHER") for i in range(5)
    ]
    gestao.post(f"/requests/{made[1]['id']}/resolve", {})
    gestao.post(f"/requests/{made[2]['id']}/start")

    everything = ids(ana.get("/requests", params={"limit": 100}))
    assert everything == [item["id"] for item in reversed(made)]
    assert ids(ana.get("/requests", params={"status": "RESOLVED"})) == [made[1]["id"]]
    assert ids(ana.get("/requests", params={"status": "IN_PROGRESS"})) == [made[2]["id"]]
    assert set(ids(ana.get("/requests", params={"category": "EVENT"}))) == {
        made[1]["id"],
        made[3]["id"],
    }
    assert ids(ana.get("/requests", params={"period": "2020-01"})) == []
    assert set(ids(ana.get("/requests", params={"period": made[0]["created_at"][:7]}))) == set(
        everything
    )

    first = ana.get("/requests", params={"limit": 2}).json()
    second = ana.get("/requests", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    third = ana.get("/requests", params={"limit": 2, "cursor": second["next_cursor"]}).json()
    walked = [item["id"] for page in (first, second, third) for item in page["items"]]
    assert walked == everything and third["next_cursor"] is None
    item = first["items"][0]
    assert set(item) == {
        "id",
        "category",
        "title",
        "status",
        "author_user_id",
        "attachments_count",
        "created_at",
        "updated_at",
        "resolved_at",
    }  # the list is light: no description, no note


@pytest.mark.parametrize(
    "params",
    [
        {"status": "DONE"},
        {"category": "NOPE"},
        {"period": "2025-13"},
        {"period": "March"},
        {"cursor": "not-a-cursor"},
        {"limit": 0},
        {"limit": 101},
    ],
)
def test_a_bad_filter_is_a_422(scene: Scene, params: dict[str, Any]) -> None:
    gestao = manager(scene)

    response = gestao.get("/requests", params=params)

    assert response.status_code == 422, response.text


def test_the_management_starts_then_resolves_with_a_note_the_author_reads(scene: Scene) -> None:
    author = scene.person("staff", label="author")
    gestao = manager(scene)
    request = opened(author)

    started = gestao.post(f"/requests/{request['id']}/start")
    resolved = gestao.post(
        f"/requests/{request['id']}/resolve", {"note": "  Comprado, chega na segunda.  "}
    )

    assert started.status_code == 200, started.text
    assert started.json()["status"] == "IN_PROGRESS"
    assert started.json()["started_by_user_id"] == str(gestao.user.id)
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["status"] == "RESOLVED" and body["resolved_by_user_id"] == str(gestao.user.id)
    assert body["resolution_note"] == "Comprado, chega na segunda."
    assert body["resolved_at"] is not None and body["started_at"] is not None
    read_by_author = author.get(f"/requests/{request['id']}").json()
    assert read_by_author["resolution_note"] == "Comprado, chega na segunda."


def test_it_can_be_resolved_straight_from_open_and_without_a_note(scene: Scene) -> None:
    author = scene.person("staff", label="author")
    gestao = manager(scene)
    request = opened(author)

    response = gestao.post(f"/requests/{request['id']}/resolve")  # no body at all

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "RESOLVED"
    assert response.json()["resolution_note"] is None and response.json()["started_at"] is None


@pytest.mark.parametrize("note", ["", "   ", "n" * 1001])
def test_a_bad_note_is_a_422_and_the_request_stays_open(scene: Scene, note: str) -> None:
    author = scene.person("staff", label="author")
    gestao = manager(scene)
    request = opened(author)

    response = gestao.post(f"/requests/{request['id']}/resolve", {"note": note})

    assert response.status_code == 422, response.text
    assert author.get(f"/requests/{request['id']}").json()["status"] == "OPEN"


def test_the_states_have_no_way_back_and_a_second_answer_is_a_409(scene: Scene) -> None:
    author = scene.person("staff", label="author")
    gestao = manager(scene)
    request = opened(author)
    path = f"/requests/{request['id']}"
    assert gestao.post(f"{path}/start").status_code == 200

    again = gestao.post(f"{path}/start")  # IN_PROGRESS cannot be started again
    assert (again.status_code, again.json()["code"]) == (409, "invalid_state")
    assert gestao.post(f"{path}/resolve", {}).status_code == 200
    for action in ("start", "resolve", "cancel"):
        client = author if action == "cancel" else gestao
        response = client.post(f"{path}/{action}")
        assert (response.status_code, response.json()["code"]) == (409, "invalid_state"), action
    assert author.get(path).json()["status"] == "RESOLVED"


def test_the_author_cancels_while_it_is_open_and_nobody_else_does(scene: Scene) -> None:
    author = scene.person("staff", label="author")
    colleague = scene.person("staff", label="colleague")
    director = scene.person("school_admin", label="director")  # may submit, but did not write it
    request = opened(author)
    path = f"/requests/{request['id']}"

    assert colleague.post(f"{path}/cancel").status_code == 404  # cannot even see it
    refused = director.post(f"{path}/cancel")
    assert (refused.status_code, refused.json()["code"]) == (403, "author_only")
    done = author.post(f"{path}/cancel")

    assert done.status_code == 200 and done.json()["status"] == "CANCELLED"
    assert director.post(f"{path}/start").status_code == 409  # a cancelled request cannot be taken


def test_a_request_in_progress_can_be_cancelled_by_its_author(scene: Scene) -> None:
    author = scene.person("staff", label="author")
    gestao = manager(scene)
    request = opened(author)
    gestao.post(f"/requests/{request['id']}/start")

    assert author.post(f"/requests/{request['id']}/cancel").json()["status"] == "CANCELLED"


def test_what_a_person_does_is_audited_without_free_text(scene: Scene) -> None:
    author = scene.person("staff", label="author")
    gestao = manager(scene)
    request = opened(author, title="Titulo secreto XYZ", description="Descricao secreta XYZ")
    gestao.post(f"/requests/{request['id']}/resolve", {"note": "Nota secreta XYZ"})

    events = scene.audit(request["id"])

    actions = [row.action for row in events]
    assert "request.created" in actions and "request.resolved" in actions
    assert "staff_requests.insert" in actions and "staff_requests.update" in actions
    assert {row.actor_type for row in events} == {"USER"}
    assert {row.actor_user_id for row in events} == {author.user.id, gestao.user.id}
    with scene.engine.connect() as connection:
        everything: str = connection.execute(
            text(
                "SELECT coalesce(string_agg(after_data::text "
                "|| coalesce(before_data::text, ''), ' '), '') "
                "FROM audit_logs WHERE entity_id = :id"
            ),
            {"id": request["id"]},
        ).scalar_one()
    assert "XYZ" not in everything  # the title, the description and the note are never copied

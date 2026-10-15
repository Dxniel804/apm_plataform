"""Reading a receipt: a photo in, a SUGGESTION out. Nothing is stored, nothing is created, the text
of the receipt never comes back, and the cheap refusals come before the model is asked."""

import datetime as dt
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import text

from app.ocr.provider import (
    FakeOcrProvider,
    OcrTimeoutError,
    OcrUnavailableError,
    RawExtraction,
    RawField,
)
from tests.expenses.support import Client, Scene, jpeg, pdf, png, stored_files, webp
from tests.ocr.conftest import OpenGate, make_runtime

READ = "/expenses/ocr"


def read(
    client: Client, content: bytes | None = None, *, name: str = "nota.jpg", **kwargs: Any
) -> Any:
    return client.post(
        READ,
        files={"file": (name, jpeg() if content is None else content, "application/octet-stream")},
        **kwargs,
    )


def audit_rows(scene: Scene, person: Client) -> list[Any]:
    """The readings this person asked for (the school is shared by every test of the session)."""
    with scene.engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    "SELECT action, entity_type, entity_id, after_data, actor_type FROM audit_logs "
                    "WHERE action = 'expense.ocr_requested' AND actor_user_id = :u "
                    "ORDER BY occurred_at"
                ),
                {"u": person.user.id},
            ).all()
        )


# --- what comes back ----------------------------------------------------------------------------


@pytest.mark.parametrize("make", [png, jpeg, webp], ids=["png", "jpeg", "webp"])
def test_a_photo_is_read_into_a_suggestion_and_nothing_is_stored(
    ocr_scene: Callable[..., Scene], make: Callable[[], bytes]
) -> None:
    provider = FakeOcrProvider()
    scene = ocr_scene(make_runtime(provider))
    staff = scene.person("staff", label="staff")
    content = make()

    response = read(staff, content, name="qualquer.bin")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "amount_cents": 8750,
        "occurred_on": "2026-09-10",
        "vendor": "PAPELARIA CENTRAL LTDA",
        "document_number": "12.345.678/0001-90",
        "confidence": {"amount": 0.95, "date": 0.9, "vendor": 0.7, "document": 0.85},
        "model": "fake",
        "elapsed_ms": 1,
    }
    assert provider.calls and provider.calls[0][0] == len(content)
    assert stored_files(scene.directory) == []  # no file, no expense
    assert staff.get("/expenses").json()["items"] == []


def test_the_text_of_the_receipt_is_never_returned_or_audited(
    ocr_scene: Callable[..., Scene],
) -> None:
    answer = RawExtraction(
        fields={
            "total_cents": RawField(1000, 0.9),
            "text": RawField("CPF 123.456.789-09 cartao 4111 1111 1111 1111", 1.0),
            "merchant": RawField("LOJA", 0.5),
        },
        model="m",
    )
    scene = ocr_scene(make_runtime(FakeOcrProvider(answer)))
    staff = scene.person("staff", label="staff")

    response = read(staff)

    assert "123.456.789-09" not in response.text and "4111" not in response.text
    rows = audit_rows(scene, staff)
    assert len(rows) == 1
    assert rows[0].entity_type == "expense_ocr" and rows[0].entity_id is None
    assert rows[0].actor_type == "USER"
    assert rows[0].after_data["outcome"] == "ok"
    assert set(rows[0].after_data["fields_found"]) == {"amount", "vendor"}
    assert "4111" not in str(rows[0].after_data)


def test_every_reading_is_audited_even_when_the_model_fails(
    ocr_scene: Callable[..., Scene],
) -> None:
    scene = ocr_scene(make_runtime(FakeOcrProvider(error=OcrUnavailableError())))
    staff = scene.person("staff", label="staff")

    assert read(staff).status_code == 503

    (row,) = audit_rows(scene, staff)
    assert row.after_data["outcome"] == "unavailable"


# --- the status ---------------------------------------------------------------------------------


def test_the_status_says_whether_the_reading_is_on(ocr_scene: Callable[..., Scene]) -> None:
    on = ocr_scene(make_runtime(FakeOcrProvider())).person("staff", label="a")
    off = ocr_scene(make_runtime(None)).person("staff", label="b")

    assert on.get(READ).json() == {"enabled": True}
    assert off.get(READ).json() == {"enabled": False}


# --- when the feature is off or the model fails -------------------------------------------------


def test_with_the_reading_off_it_is_a_503_and_nothing_is_asked(
    ocr_scene: Callable[..., Scene],
) -> None:
    scene = ocr_scene(make_runtime(None))
    staff = scene.person("staff", label="staff")

    response = read(staff)

    assert (response.status_code, response.json()["code"]) == (503, "ocr_unavailable")
    assert audit_rows(scene, staff) == []


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (OcrTimeoutError(), 504, "ocr_timeout"),
        (OcrUnavailableError(), 503, "ocr_unavailable"),
    ],
)
def test_a_model_that_fails_is_a_problem_the_form_can_survive(
    ocr_scene: Callable[..., Scene], error: Exception, status: int, code: str
) -> None:
    scene = ocr_scene(make_runtime(FakeOcrProvider(error=error)))
    staff = scene.person("staff", label="staff")

    response = read(staff)

    assert (response.status_code, response.json()["code"]) == (status, code)
    assert response.headers["content-type"].startswith("application/problem+json")
    # and the person can still write the expense by hand
    assert staff.get("/expense-categories").status_code == 200


def test_a_busy_reading_says_so_with_retry_after(ocr_scene: Callable[..., Scene]) -> None:
    scene = ocr_scene(make_runtime(FakeOcrProvider(), gate=OpenGate(1)))
    staff = scene.person("staff", label="staff")

    response = read(staff)

    assert (response.status_code, response.json()["code"]) == (503, "ocr_busy")
    assert response.headers["retry-after"] == "5"


def test_the_slot_is_freed_even_when_the_model_fails(ocr_scene: Callable[..., Scene]) -> None:
    provider = FakeOcrProvider(error=OcrUnavailableError())
    from app.ocr.limits import ConcurrencyGate

    gate = ConcurrencyGate(1)
    scene = ocr_scene(make_runtime(provider, gate=gate))
    staff = scene.person("staff", label="staff")

    for _ in range(3):  # one slot, three failures: it would be stuck if it were not released
        assert read(staff).status_code == 503


# --- the brakes ---------------------------------------------------------------------------------


def test_a_person_may_read_only_so_many_in_a_minute(ocr_scene: Callable[..., Scene]) -> None:
    provider = FakeOcrProvider()
    scene = ocr_scene(make_runtime(provider, per_minute=2))
    ana = scene.person("staff", label="ana")
    beto = scene.person("staff", label="beto")

    assert read(ana).status_code == 200
    assert read(ana).status_code == 200
    blocked = read(ana)

    assert (blocked.status_code, blocked.json()["code"]) == (429, "rate_limited")
    assert 1 <= int(blocked.headers["retry-after"]) <= 61
    assert len(provider.calls) == 2  # the third never reached the model
    assert read(beto).status_code == 200  # somebody else is not slowed down


# --- what may be sent ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "name"),
    [
        (pdf(), "nota.pdf"),
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "nota.png"),
        (b"<html></html>", "nota.jpg"),
        (b"plain text", "nota.png"),
    ],
    ids=["pdf", "svg", "html", "text"],
)
def test_only_photos_are_read_whatever_the_name_says(
    ocr_scene: Callable[..., Scene], content: bytes, name: str
) -> None:
    provider = FakeOcrProvider()
    staff = ocr_scene(make_runtime(provider)).person("staff", label="staff")

    response = read(staff, content, name=name)

    assert (response.status_code, response.json()["code"]) == (415, "attachment_type_not_allowed")
    assert provider.calls == []


def test_an_empty_file_and_a_missing_file_are_a_422(ocr_scene: Callable[..., Scene]) -> None:
    staff = ocr_scene().person("staff", label="staff")

    assert read(staff, b"").status_code == 422
    assert staff.post(READ, data={"other": "x"}).status_code == 422


def test_a_file_over_the_limit_is_a_413_and_never_reaches_the_model(
    ocr_scene: Callable[..., Scene],
) -> None:
    provider = FakeOcrProvider()
    scene = ocr_scene(make_runtime(provider), max_bytes=2048)
    staff = scene.person("staff", label="staff")

    response = read(staff, png() + b"0" * 4096)

    assert (response.status_code, response.json()["code"]) == (413, "payload_too_large")
    assert provider.calls == []


def test_the_request_must_declare_its_size(ocr_scene: Callable[..., Scene]) -> None:
    staff = ocr_scene().person("staff", label="staff")
    boundary = "xBOUNDARYx"
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.png"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode()
        + png()
        + f"\r\n--{boundary}--\r\n".encode()
    )

    response = staff.raw_post(
        READ, iter([body[:50], body[50:]]), f"multipart/form-data; boundary={boundary}"
    )

    assert (response.status_code, response.json()["code"]) == (411, "length_required")


# --- who may read -------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["secretaria"])
def test_only_who_can_send_an_expense_may_read_a_receipt(
    ocr_scene: Callable[..., Scene], role: str
) -> None:
    provider = FakeOcrProvider()
    person = ocr_scene(make_runtime(provider)).person(role, label=role)

    for response in (read(person), person.get(READ)):
        assert (response.status_code, response.json()["code"]) == (403, "permission_denied")
    assert provider.calls == []


def test_a_secretaria_does_not_read_receipts_because_she_never_writes_expenses(
    ocr_scene: Callable[..., Scene],
) -> None:
    secretaria = ocr_scene().person("secretaria", label="secretaria")

    assert read(secretaria).status_code == 403


def test_a_school_outside_the_session_is_the_usual_404(ocr_scene: Callable[..., Scene]) -> None:
    scene = ocr_scene()
    ana = scene.person("staff", school="1", label="ana")
    other = scene.person("staff", school="2", label="other")

    for school in (other.school, scene.world.school_b1):
        assert read(ana, school=school).status_code == 404
        assert ana.get(READ, school=school).status_code == 404


def test_without_a_session_it_is_a_401(ocr_scene: Callable[..., Scene]) -> None:
    scene = ocr_scene()
    anonymous = scene.apis.make(configure=scene._configure)

    response = anonymous.client.get(f"/api/v1/schools/{scene.world.school_a1}{READ}")

    assert response.status_code == 401


# --- the answer of the model is only data -------------------------------------------------------


def test_what_the_model_says_is_validated_before_the_form_sees_it(
    ocr_scene: Callable[..., Scene],
) -> None:
    today = dt.datetime.now(dt.UTC).date()
    future = (today + dt.timedelta(days=30)).isoformat()
    cases: list[tuple[dict[str, RawField], dict[str, Any]]] = [
        (
            {"total_cents": RawField(-5, 0.9), "date": RawField(future, 0.9)},
            {"amount_cents": None, "occurred_on": None},
        ),
        (
            {"total_cents": RawField(10**12, 0.9), "date": RawField("2001-01-01", 0.9)},
            {"amount_cents": None, "occurred_on": None},
        ),
        (
            {"total_cents": RawField(True, 0.9), "date": RawField("10/09/2026", 0.9)},
            {"amount_cents": None, "occurred_on": None},
        ),
        (
            {"total_cents": RawField("8750", 0.9), "date": RawField("2026-02-31", 0.9)},
            {"amount_cents": None, "occurred_on": None},
        ),
        (
            {
                "merchant": RawField("A\x00B\x07C\n D   E", 0.9),
                "document_number": RawField("<script>", 0.9),
            },
            {"vendor": "ABC D E", "document_number": None},
        ),
        (
            {"merchant": RawField("x" * 500, 0.9), "unknown": RawField("whatever", 1.0)},
            {"vendor": "x" * 200},
        ),
        (
            {"total_cents": RawField(1500, 7.5), "merchant": RawField("   ", 0.9)},
            {"amount_cents": 1500, "vendor": None},
        ),
    ]
    for fields, expected in cases:
        scene = ocr_scene(make_runtime(FakeOcrProvider(RawExtraction(fields=fields, model="m"))))
        staff = scene.person("staff", label="staff")

        response = read(staff)

        assert response.status_code == 200, (fields, response.text)
        body = response.json()
        for key, value in expected.items():
            assert body[key] == value, (fields, key)
        if body["amount_cents"] is None:
            assert body["confidence"]["amount"] == 0  # a field that failed carries no confidence
        assert 0 <= max(body["confidence"].values()) <= 1  # 7.5 was clamped

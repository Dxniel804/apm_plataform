"""The photos: the type comes from the bytes, the size is bounded, the hash is of the bytes, the
file lives behind the store, and only whoever can see the request can download it."""

import hashlib
from collections.abc import Callable
from typing import Any

import pytest

from tests.expenses.support import Scene, jpeg, pdf, png, stored_files, webp
from tests.staff_requests.support import manager, opened, with_photo


def upload(
    client: Any, request_id: str, content: bytes, *, name: str = "foto.png", **kwargs: Any
) -> Any:
    return client.post(
        f"/requests/{request_id}/attachments",
        files={"file": (name, content, "application/octet-stream")},
        **kwargs,
    )


@pytest.mark.parametrize(
    ("content", "media_type"),
    [(png(), "image/png"), (jpeg(), "image/jpeg"), (webp(), "image/webp")],
    ids=["png", "jpeg", "webp"],
)
def test_a_photo_is_stored_with_its_size_and_hash(
    scene: Scene, content: bytes, media_type: str
) -> None:
    author = scene.person("staff", label="author")
    request = opened(author)

    # whatever the client SAYS the file is (name, declared type), the bytes decide
    response = upload(author, request["id"], content, name="IMG_0001.bin")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["content_type"] == media_type
    assert body["size_bytes"] == len(content)
    assert body["sha256"] == hashlib.sha256(content).hexdigest()
    assert body["uploaded_by_user_id"] == str(author.user.id)
    assert set(body) == {
        "id",
        "file_name",
        "content_type",
        "size_bytes",
        "sha256",
        "uploaded_by_user_id",
        "created_at",
    }  # the storage key never leaves the server
    (stored,) = stored_files(scene.directory)
    assert stored.read_bytes() == content
    assert str(request["id"]) in str(stored) and str(author.school) in str(stored)
    detail = author.get(f"/requests/{request['id']}").json()
    assert detail["attachments_count"] == 1 and [a["id"] for a in detail["attachments"]] == [
        body["id"]
    ]


@pytest.mark.parametrize(
    ("content", "name"),
    [
        (pdf(), "nota.pdf"),  # photos only
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "foto.png"),
        (b"<html><script>alert(1)</script></html>", "foto.jpg"),
        (b"MZ\x90\x00 an executable", "foto.png"),
        (b"plain text", "foto.png"),
    ],
    ids=["pdf", "svg", "html", "exe", "text"],
)
def test_anything_that_is_not_a_photo_is_a_415_whatever_its_name(
    scene: Scene, content: bytes, name: str
) -> None:
    author = scene.person("staff", label="author")
    request = opened(author)

    response = upload(author, request["id"], content, name=name)

    assert (response.status_code, response.json()["code"]) == (415, "attachment_type_not_allowed")
    assert stored_files(scene.directory) == []
    assert author.get(f"/requests/{request['id']}").json()["attachments"] == []


def test_an_empty_file_is_a_422(scene: Scene) -> None:
    author = scene.person("staff", label="author")
    request = opened(author)

    response = upload(author, request["id"], b"")

    assert response.status_code == 422, response.text


def test_a_missing_file_field_is_a_422(scene: Scene) -> None:
    author = scene.person("staff", label="author")
    request = opened(author)

    response = author.post(f"/requests/{request['id']}/attachments", data={"other": "x"})

    assert response.status_code == 422, response.text


def test_a_file_over_the_limit_is_a_413_and_leaves_nothing(
    scene_with_limit: Callable[[int], Scene],
) -> None:
    scene = scene_with_limit(2048)
    author = scene.person("staff", label="author")
    request = opened(author)

    response = upload(author, request["id"], png() + b"0" * 4096)

    assert (response.status_code, response.json()["code"]) == (413, "payload_too_large")
    assert stored_files(scene.directory) == []


def test_the_request_must_declare_its_size(scene: Scene) -> None:
    author = scene.person("staff", label="author")
    request = opened(author)
    boundary = "xBOUNDARYx"
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="a.png"\r\nContent-Type: image/png\r\n\r\n'
        ).encode()
        + png()
        + f"\r\n--{boundary}--\r\n".encode()
    )

    response = author.raw_post(
        f"/requests/{request['id']}/attachments",
        iter([body[:50], body[50:]]),  # chunked: no Content-Length
        f"multipart/form-data; boundary={boundary}",
    )

    assert response.status_code == 411 and response.json()["code"] == "length_required"
    assert stored_files(scene.directory) == []


def test_the_same_photo_twice_is_a_409_and_a_seventh_one_too(scene: Scene) -> None:
    author = scene.person("staff", label="author")
    request = opened(author)
    same = png()
    assert upload(author, request["id"], same).status_code == 201

    again = upload(author, request["id"], same)
    assert (again.status_code, again.json()["code"]) == (409, "attachment_duplicate")

    for _ in range(5):
        assert upload(author, request["id"], png()).status_code == 201
    seventh = upload(author, request["id"], png())
    assert (seventh.status_code, seventh.json()["code"]) == (409, "attachment_limit")
    assert len(stored_files(scene.directory)) == 6  # the refused ones left nothing behind


def test_only_the_author_attaches_and_only_while_it_is_open(scene: Scene) -> None:
    author = scene.person("staff", label="author")
    director = scene.person("school_admin", label="director")
    gestao = manager(scene)
    request = opened(author)

    foreign = upload(director, request["id"], png())
    assert (foreign.status_code, foreign.json()["code"]) == (403, "author_only")
    assert stored_files(scene.directory) == []
    assert upload(author, request["id"], png()).status_code == 201
    gestao.post(f"/requests/{request['id']}/start")
    assert upload(author, request["id"], png()).status_code == 201  # IN_PROGRESS still takes photos
    gestao.post(f"/requests/{request['id']}/resolve", {})

    closed = upload(author, request["id"], png())

    assert (closed.status_code, closed.json()["code"]) == (409, "attachments_closed")
    assert len(stored_files(scene.directory)) == 2


def test_the_file_name_is_only_a_clean_label(scene: Scene) -> None:
    author = scene.person("staff", label="author")
    request = opened(author)

    response = upload(author, request["id"], png(), name="../../etc/passwd.png")

    assert response.status_code == 201
    assert response.json()["file_name"] == "passwd.png"
    (stored,) = stored_files(scene.directory)
    assert "passwd" not in str(stored) and ".." not in stored.relative_to(scene.directory).parts


def test_whoever_can_see_the_request_downloads_the_photo_safely(scene: Scene) -> None:
    author = scene.person("staff", label="author")
    gestao = manager(scene)
    colleague = scene.person("staff", label="colleague")
    request = opened(author)
    content = png()
    photo = upload(author, request["id"], content, name="minha foto.png").json()
    path = f"/requests/{request['id']}/attachments/{photo['id']}"

    for reader in (author, gestao):
        response = reader.get(path)
        assert response.status_code == 200, response.text
        assert response.content == content
        assert response.headers["content-type"] == "image/png"
        assert response.headers["content-disposition"].startswith("attachment;")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
        assert response.headers["cache-control"] == "private, no-store"
    assert colleague.get(path).status_code == 404
    assert author.get(f"/requests/{request['id']}/attachments/{request['id']}").status_code == 404


def test_a_photo_of_one_request_is_not_downloadable_through_another(scene: Scene) -> None:
    author = scene.person("staff", label="author")
    first, second = opened(author), opened(author, title="Outro")
    photo = with_photo(author, first["id"])

    response = author.get(f"/requests/{second['id']}/attachments/{photo['id']}")

    assert response.status_code == 404

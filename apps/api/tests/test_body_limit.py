"""A body that DECLARES more than any route accepts is refused before the route reads it."""

from tests.authsupport import ApiFactory


def test_a_declared_body_larger_than_any_route_accepts_is_refused_before_it_is_read(
    apis: ApiFactory,
) -> None:
    api = apis.make()

    webhook = api.client.post(
        "/api/v1/webhooks/pix/sandbox",
        content=b"{}",
        headers={"Content-Length": str(65 * 1024), "Content-Type": "application/json"},
    )
    big = api.client.post(
        "/api/v1/auth/login",
        content=b"{}",
        headers={"Content-Length": str(25 * 1024 * 1024), "Content-Type": "application/json"},
    )

    assert webhook.status_code == 413 and webhook.json()["code"] == "payload_too_large"
    assert big.status_code == 413

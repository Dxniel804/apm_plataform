"""What ANY Pix provider adapter must do, written once. The sandbox passes it today; the adapter of
the real gateway is added to `ADAPTERS` (with the way to make a payment happen in ITS sandbox) and
must pass the same tests before it is allowed anywhere near a real charge."""

import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import ProblemError
from app.pix import provider as provider_module
from app.pix.provider import (
    REAL_PROVIDERS,
    ChargeTarget,
    PixProvider,
    SandboxPixProvider,
    get_provider,
    live_payments_enabled,
)

E2E = re.compile(r"^E[A-Za-z0-9]{31}$")


Pay = Callable[[str, int | None], None]
Make = Callable[[], tuple[PixProvider, Pay]]


def _sandbox() -> tuple[PixProvider, Pay]:
    fake = SandboxPixProvider()

    def pay(txid: str, amount: int | None) -> None:
        fake.simulate_payment(txid, amount)

    return fake, pay


# (name, build the adapter, and how to make a payment of `amount` (None: the exact one) happen).
ADAPTERS = [pytest.param(_sandbox, id="sandbox")]


def _target() -> ChargeTarget:
    return ChargeTarget(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())


def _txid() -> str:
    return uuid.uuid4().hex


@pytest.mark.parametrize("make", ADAPTERS)
def test_a_new_charge_carries_the_code_to_pay_and_is_pending(make: Make) -> None:
    adapter, _ = make()
    target, txid = _target(), _txid()
    expires = datetime.now(UTC) + timedelta(minutes=30)

    charge = adapter.create_charge(target, txid=txid, amount_cents=3000, expires_at=expires)
    seen = adapter.fetch_payment(target, txid)

    assert charge.txid == txid and charge.emv_payload and charge.expires_at == expires
    assert seen is not None and seen.status == "PENDING" and seen.received_amount_cents is None


@pytest.mark.parametrize("make", ADAPTERS)
def test_the_provider_does_not_know_a_charge_of_another_school(make: Make) -> None:
    adapter, _ = make()
    target, txid = _target(), _txid()
    adapter.create_charge(
        target, txid=txid, amount_cents=3000, expires_at=datetime.now(UTC) + timedelta(minutes=30)
    )

    assert adapter.fetch_payment(_target(), txid) is None  # another school, same txid
    assert adapter.fetch_payment(target, _txid()) is None  # a txid it never saw


@pytest.mark.parametrize("make", ADAPTERS)
def test_a_paid_charge_says_how_much_when_and_the_end_to_end_id(make: Make) -> None:
    adapter, pay = make()
    target, txid = _target(), _txid()
    adapter.create_charge(
        target, txid=txid, amount_cents=3000, expires_at=datetime.now(UTC) + timedelta(minutes=30)
    )

    pay(txid, None)
    paid = adapter.fetch_payment(target, txid)

    assert paid is not None and paid.status == "PAID" and paid.received_amount_cents == 3000
    assert paid.paid_at is not None and paid.paid_at <= datetime.now(UTC)
    assert paid.end_to_end_id is not None and E2E.fullmatch(paid.end_to_end_id)
    assert paid.fee_cents is None or 0 <= paid.fee_cents <= 3000  # never more than the payment


@pytest.mark.parametrize("make", ADAPTERS)
def test_a_payment_of_another_amount_is_reported_as_it_was_received(make: Make) -> None:
    adapter, pay = make()
    target, txid = _target(), _txid()
    adapter.create_charge(
        target, txid=txid, amount_cents=3000, expires_at=datetime.now(UTC) + timedelta(minutes=30)
    )

    pay(txid, 2000)

    paid = adapter.fetch_payment(target, txid)
    assert paid is not None and paid.received_amount_cents == 2000  # the webhook compares it


@pytest.mark.parametrize("make", ADAPTERS)
def test_an_unpaid_charge_past_its_time_is_expired(make: Make) -> None:
    adapter, _ = make()
    target, txid = _target(), _txid()
    adapter.create_charge(
        target, txid=txid, amount_cents=3000, expires_at=datetime.now(UTC) - timedelta(seconds=1)
    )

    seen = adapter.fetch_payment(target, txid)

    assert seen is not None and seen.status == "EXPIRED"


# --- who may be served ----------------------------------------------------------------------


def test_the_sandbox_is_served_outside_production_and_never_in_it() -> None:
    assert get_provider("SANDBOX", "development") is provider_module.sandbox_provider()
    with pytest.raises(ProblemError) as refused:
        get_provider("SANDBOX", "production")
    assert refused.value.status == 501


def test_a_real_provider_needs_its_adapter_and_the_kill_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake, _ = _sandbox()
    with pytest.raises(ProblemError) as missing:
        get_provider("ASAAS", "production")
    assert missing.value.status == 501  # no adapter written yet

    monkeypatch.setitem(REAL_PROVIDERS, "ASAAS", lambda: fake)
    monkeypatch.delenv("PIX_LIVE_ENABLED", raising=False)
    with pytest.raises(ProblemError) as paused:
        get_provider("ASAAS", "production")
    assert paused.value.status == 503 and paused.value.code == "payments_paused"

    monkeypatch.setenv("PIX_LIVE_ENABLED", "true")
    assert live_payments_enabled() and get_provider("ASAAS", "production") is fake


@pytest.mark.parametrize("value", ["", "false", "0", "TRUE ", "yes"])
def test_only_the_word_true_turns_live_payments_on(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("PIX_LIVE_ENABLED", value)

    assert live_payments_enabled() is (value.strip().lower() == "true")

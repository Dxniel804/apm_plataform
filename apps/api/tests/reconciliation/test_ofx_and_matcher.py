# ruff: noqa: E501  (statements and long assertions)
"""The reader of OFX and the pairing function: pure code, no database."""

import uuid
from datetime import date

import pytest

from app.reconciliation.matcher import BankLine, LedgerItem, pair
from app.reconciliation.ofx import MAX_LINES, OfxError, parse_ofx
from tests.reconciliation.ofx_samples import e2e, sgml, xml

D = date(2026, 10, 5)


def test_it_reads_the_sgml_flavour_of_a_brazilian_bank() -> None:
    data = sgml(
        [
            ("0001", D, "35.00", f"PIX RECEBIDO {e2e(7)} CPF 123.456.789-09"),
            ("0002", D, "-80,50", "TARIFA PIX"),
        ],
        date(2026, 10, 1),
        date(2026, 10, 31),
    )

    statement = parse_ofx(data)

    assert [(ln.bank_ref, ln.amount_cents) for ln in statement.lines] == [
        ("0001", 3500),
        ("0002", -8050),
    ]  # the comma is a decimal point
    assert statement.period_start == date(2026, 10, 1) and statement.period_end == date(
        2026, 10, 31
    )
    assert statement.closing_balance_cents == 123456
    assert statement.lines[0].end_to_end_id == e2e(7)
    assert statement.lines[0].posted_on == D  # the time and the zone after the day are ignored


def test_it_reads_the_xml_flavour_the_same_way() -> None:
    statement = parse_ofx(
        xml([("a1", D, "-12.30", "COMPRA CARTAO")], date(2026, 10, 1), date(2026, 10, 31))
    )

    assert [(ln.bank_ref, ln.amount_cents, ln.memo) for ln in statement.lines] == [
        ("a1", -1230, "COMPRA CARTAO")
    ]
    assert statement.closing_balance_cents == 1000


def test_the_cpf_and_the_cnpj_in_the_text_are_masked_and_the_text_is_short() -> None:
    memo = "TED 123.456.789-09 E 12.345.678/0001-95 11122233344 " + "x" * 300
    statement = parse_ofx(sgml([("1", D, "10.00", memo)], D, D))

    shown = statement.lines[0].memo
    assert "123.456.789" not in shown and "12.345.678" not in shown and "11122233344" not in shown
    assert shown.count("***") == 3 and len(shown) <= 120


def test_the_end_to_end_id_is_not_taken_for_a_document_and_a_fee_is_recognized() -> None:
    statement = parse_ofx(
        sgml(
            [
                ("1", D, "-0.80", f"TARIFA PIX {e2e(12345678901)}"),
                ("2", D, "-50.00", "PAGAMENTO FORNECEDOR"),
            ],
            D,
            D,
        )
    )

    assert (
        statement.lines[0].end_to_end_id == e2e(12345678901)
        and statement.lines[0].looks_like_fee is True
    )
    assert statement.lines[1].looks_like_fee is False


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"hello", "not_ofx"),
        (b"<OFX></OFX>", "no_lines"),
        (
            sgml([("1", D, "10.00", "x")], D, D).replace(b"<TRNAMT>10.00", b"<TRNAMT>dez"),
            "bad_line",
        ),
        (sgml([("1", D, "10.005", "x")], D, D), "bad_line"),  # three decimals: not money
        (sgml([("1", D, "10.00", "x")], D, D).replace(b"<FITID>1", b"<FITID>"), "bad_line"),
        (sgml([("1", D, "10.00", "x")], D, D).replace(b"20261005120000", b"20261399"), "bad_line"),
        (b"x" * (2 * 1024 * 1024 + 1), "file_too_large"),
    ],
)
def test_a_file_that_cannot_be_trusted_is_refused_with_a_code(data: bytes, code: str) -> None:
    with pytest.raises(OfxError) as error:
        parse_ofx(data)
    assert error.value.code == code


def test_a_statement_has_a_limit_of_lines_and_zero_lines_are_skipped() -> None:
    many = [(str(i), D, "1.00", "x") for i in range(MAX_LINES + 1)]
    with pytest.raises(OfxError) as error:
        parse_ofx(sgml(many, D, D))
    assert error.value.code == "too_many_lines"
    assert len(parse_ofx(sgml([("1", D, "0.00", "x"), ("2", D, "5.00", "y")], D, D)).lines) == 1


def test_an_entity_in_the_file_is_just_text() -> None:
    bomb = b'<!DOCTYPE x [<!ENTITY a "AAAA">]><OFX><STMTTRN><DTPOSTED>20261005<TRNAMT>1.00<FITID>1<MEMO>&a;</STMTTRN></OFX>'
    assert parse_ofx(bomb).lines[0].memo == "&a;"  # nothing is expanded, nothing is fetched


# --- the pairing -------------------------------------------------------------------------------------


def line(amount: int, day: date = D, e2e_id: str | None = None) -> BankLine:
    return BankLine(uuid.uuid4(), day, amount, e2e_id)


def item(
    amount: int, day: date = D, e2e_id: str | None = None, net: int | None = None, code: int = 1
) -> LedgerItem:
    return LedgerItem(uuid.uuid4(), code, "CONTRIBUTION", day, amount, net, e2e_id)


def test_the_end_to_end_id_pairs_even_when_the_dates_are_far_apart() -> None:
    bank, ledger = line(3000, date(2026, 10, 20), e2e(1)), item(3000, D, e2e(1))

    result = pair([bank], [ledger])

    assert (
        result.matched == [(bank, ledger)] and not result.divergences and not result.missing_in_bank
    )


def test_the_net_amount_pairs_a_payment_whose_fee_was_kept_by_the_gateway() -> None:
    bank, ledger = line(2920, D, e2e(2)), item(3000, D, e2e(2), net=2920)

    assert pair([bank], [ledger]).matched == [(bank, ledger)]


def test_same_end_to_end_id_with_another_amount_is_a_divergence_not_a_guess() -> None:
    bank, ledger = line(100, D, e2e(3)), item(3000, D, e2e(3))

    result = pair([bank], [ledger])

    assert not result.matched and [d.reason for d in result.divergences] == ["amount_differs"]
    assert not result.missing_in_bank  # the entry is accounted for: a person decides


def test_amount_and_date_pair_one_to_one_inside_the_window() -> None:
    inside, far = item(1500, D, code=1), item(1500, date(2026, 10, 20), code=2)
    bank = line(1500, date(2026, 10, 7))

    result = pair([bank], [inside, far])

    assert result.matched == [(bank, inside)] and result.missing_in_bank == [far]


def test_two_equal_candidates_are_ambiguous_for_both_sides() -> None:
    a, b = item(1500, code=1), item(1500, code=2)
    one, two = line(1500), line(1500)

    result = pair([one, two], [a, b])

    assert (
        not result.matched
        and len(result.divergences) == 2
        and all(d.reason == "ambiguous" for d in result.divergences)
    )
    assert not result.missing_in_bank and not result.missing_in_system


def test_one_line_for_one_entry_with_a_rival_line_is_ambiguous_too() -> None:
    result = pair([line(900), line(900)], [item(900)])

    assert not result.matched and len(result.divergences) == 2


def test_what_has_no_pair_is_listed_on_the_side_it_is_missing() -> None:
    bank, ledger = line(777), item(3333)

    result = pair([bank], [ledger])

    assert result.missing_in_system == [bank] and result.missing_in_bank == [ledger]


def test_in_and_out_never_pair_with_each_other() -> None:
    assert pair([line(-3000)], [item(3000)]).matched == []


def test_the_answer_does_not_depend_on_the_order() -> None:
    lines = [line(100 * i, date(2026, 10, i)) for i in range(1, 6)]
    items = [item(100 * i, date(2026, 10, i), code=i) for i in range(1, 6)]

    forward = pair(lines, items)
    backward = pair(list(reversed(lines)), list(reversed(items)))

    assert sorted((a.line_id, b.transaction_id) for a, b in forward.matched) == sorted(
        (a.line_id, b.transaction_id) for a, b in backward.matched
    )
    assert len(forward.matched) == 5

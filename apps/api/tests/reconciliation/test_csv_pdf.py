# ruff: noqa: E501  (statements)
"""Statements in CSV and PDF: the columns are found (or mapped by hand and kept), a PDF is a
best-effort reading and every line of it must be conferred before it becomes an entry."""

import io
from datetime import date, timedelta
from typing import Any

import pytest
from reportlab.pdfgen import canvas
from sqlalchemy import Engine

from app.reconciliation.csv_statement import CsvError, detect, parse_csv, profile_from_dict
from app.reconciliation.pdf_statement import PdfError, parse_pdf
from tests.authsupport import ApiFactory
from tests.campaigns.support import committed_manager
from tests.expenses.support import Client
from tests.public.conftest import PublicSchool
from tests.reconciliation.ofx_samples import e2e

BB = (
    "Data;Histórico;Documento;Valor;Saldo\r\n"
    "03/10/2026;Compra material de escritório;123;-189,90;1.000,00\r\n"
    "08/10/2026;Transferência recebida;124;1.250,00;2.250,00\r\n"
    "08/10/2026;Tarifa bancária;125;-42,90;2.207,10\r\n"
).encode("cp1252")
SPLIT = (
    "Data,Descrição,Crédito,Débito\n"
    f"2026-10-03,PIX RECEBIDO {e2e(5)} MARIA,30.00,\n"
    "2026-10-04,TARIFA PIX,,0.80\n"
).encode()


def test_a_csv_with_one_column_of_amounts_is_detected_and_read() -> None:
    header, sample, profile = detect(BB)

    assert header is not None and header[1] == "Histórico"
    assert profile is not None and profile.delimiter == ";" and profile.decimal == ","
    assert profile.amount_col == 3 and profile.date_col == 0 and profile.memo_col == 1
    statement = parse_csv(BB, profile)
    assert [(ln.posted_on, ln.amount_cents) for ln in statement.lines] == [
        (date(2026, 10, 3), -18990),
        (date(2026, 10, 8), 125000),
        (date(2026, 10, 8), -4290),
    ]
    assert statement.lines[2].looks_like_fee
    assert (statement.period_start, statement.period_end) == (date(2026, 10, 3), date(2026, 10, 8))


def test_a_csv_with_credit_and_debit_columns_and_iso_dates() -> None:
    _, _, profile = detect(SPLIT)

    assert profile is not None and profile.credit_col == 2 and profile.debit_col == 3
    assert profile.date_order == "YMD" and profile.decimal == "."
    lines = parse_csv(SPLIT, profile).lines
    assert [ln.amount_cents for ln in lines] == [3000, -80]
    assert lines[0].end_to_end_id == e2e(5)


def test_the_same_identical_lines_get_distinct_ids_and_the_same_file_the_same_ids() -> None:
    data = ("Data;Descrição;Valor\n05/10/2026;PIX;10,00\n05/10/2026;PIX;10,00\n").encode()
    _, _, profile = detect(data)
    assert profile is not None

    first = [ln.bank_ref for ln in parse_csv(data, profile).lines]
    again = [ln.bank_ref for ln in parse_csv(data, profile).lines]

    assert len(set(first)) == 2 and first == again


@pytest.mark.parametrize(
    "raw",
    [None, "x", {"delimiter": "|", "date_order": "DMY", "decimal": ",", "date_col": 0, "memo_col": 1, "amount_col": 2},
     {"delimiter": ";", "date_order": "DMY", "decimal": ",", "date_col": 0, "memo_col": 1},
     {"delimiter": ";", "date_order": "DMY", "decimal": ",", "date_col": 999, "memo_col": 1, "amount_col": 2}],
)  # fmt: skip
def test_a_profile_that_is_not_valid_is_refused(raw: Any) -> None:
    with pytest.raises(CsvError):
        profile_from_dict(raw)


def test_a_file_with_no_dates_cannot_be_detected() -> None:
    header, sample, profile = detect(b"a;b;c\nx;y;z\n")

    assert profile is None and sample


def _pdf(lines: list[str]) -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer)
    y = 800
    for line in lines:
        page.drawString(40, y, line)
        y -= 16
    page.save()
    return buffer.getvalue()


def test_a_pdf_with_text_is_read_and_a_line_without_a_clear_sign_is_left_out() -> None:
    data = _pdf(
        [
            "Extrato de 01/10/2026 a 31/10/2026",
            "05/10 PIX RECEBIDO MARIA 30,00 C",
            "06/10 TARIFA PIX 0,80 D",
            "07/10 AJUSTE 5,00",
            "08/10/2026 PAGAMENTO BOLETO PAPELARIA -150,00",
        ]
    )

    lines = parse_pdf(data).lines

    assert [(ln.posted_on, ln.amount_cents) for ln in lines] == [
        (date(2026, 10, 5), 3000),
        (date(2026, 10, 6), -80),
        (date(2026, 10, 8), -15000),
    ]


def test_a_pdf_without_text_or_without_a_year_is_refused() -> None:
    with pytest.raises(PdfError) as empty:
        parse_pdf(_pdf([]))
    with pytest.raises(PdfError) as noyear:
        parse_pdf(_pdf(["05/10 PIX RECEBIDO 30,00 C"]))
    with pytest.raises(PdfError) as junk:
        parse_pdf(b"%PDF-1.4 not really")

    assert (empty.value.code, noyear.value.code, junk.value.code) == (
        "pdf_without_text",
        "pdf_year_unknown",
        "not_pdf",
    )


# --- through the API ---------------------------------------------------------------------------------


def _account(gestao: Client) -> str:
    return str(
        gestao.post(
            "/reconciliation/accounts", {"nickname": "Conta principal", "bank_name": "Banco"}
        ).json()["id"]
    )


def _send(gestao: Client, account: str, data: bytes, name: str, profile: str | None = None) -> Any:
    form = {"bank_account_id": account, **({} if profile is None else {"profile": profile})}
    return gestao.post(
        "/reconciliation/imports",
        data=form,
        files={"file": (name, data, "application/octet-stream")},
    )


def test_a_csv_is_imported_and_its_columns_are_kept_on_the_account(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    account = _account(gestao)

    preview = gestao.post(
        "/reconciliation/imports/preview",
        data={"bank_account_id": account},
        files={"file": ("extrato.csv", BB, "text/csv")},
    )
    sent = _send(
        gestao,
        account,
        BB,
        "extrato.csv",
        profile=__import__("json").dumps(preview.json()["suggested_profile"]),
    )

    assert preview.status_code == 200 and preview.json()["kind"] == "CSV"
    assert preview.json()["suggested_profile"]["amount_col"] == 3
    assert sent.status_code == 201, sent.text
    assert sent.json()["source"] == "CSV" and sent.json()["line_count"] == 3
    saved = gestao.get("/reconciliation/accounts").json()[0]["csv_profile"]
    assert saved["amount_col"] == 3
    # the next file of the account needs no map
    more = BB + b"09/10/2026;Pagamento de internet;126;-75,50;2.131,60\r\n"
    assert _send(gestao, account, more, "outro.csv").status_code == 201


def test_a_csv_that_cannot_be_detected_asks_for_the_map(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    account = _account(gestao)

    answer = _send(gestao, account, b"a;b;c\nx;y;z\n", "estranho.csv")

    assert answer.status_code == 422 and answer.json()["code"] == "csv_needs_mapping"


def test_a_pdf_line_must_be_conferred_before_it_becomes_an_entry(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)
    account = _account(gestao)
    day = date.today() - timedelta(days=2)
    pdf = _pdf(
        [
            f"Extrato {day:%d/%m/%Y}",
            f"{day:%d/%m/%Y} TARIFA PIX 0,80 D",
            f"{day:%d/%m/%Y} PIX RECEBIDO JOANA 10,00 C",
        ]
    )

    sent = _send(gestao, account, pdf, "extrato.pdf")
    body = gestao.get(f"/reconciliation/imports/{sent.json()['id']}").json()
    fee = next(ln for ln in body["missing_in_system"] if "TARIFA" in ln["memo"])

    assert sent.status_code == 201 and sent.json()["source"] == "PDF"
    assert fee["needs_review"] is True
    unreviewed = gestao.post(
        f"/reconciliation/lines/{fee['line_id']}/actions", {"action": "REGISTER_FEE"}
    )
    ignored = gestao.post(
        f"/reconciliation/lines/{[ln for ln in body['missing_in_system'] if 'JOANA' in ln['memo']][0]['line_id']}/actions",
        {"action": "IGNORE", "reason": "Já lançado antes"},
    )
    done = gestao.post(
        f"/reconciliation/lines/{fee['line_id']}/actions",
        {"action": "REGISTER_FEE", "reviewed": True},
    )

    assert unreviewed.status_code == 422
    assert ignored.status_code == 201  # ignoring creates no entry: no review needed
    assert done.status_code == 201, done.text


def test_a_scanned_pdf_is_refused_with_a_clear_code(
    apis: ApiFactory, school: PublicSchool, admin_engine: Engine
) -> None:
    gestao = committed_manager(apis, admin_engine, school)

    answer = _send(gestao, _account(gestao), _pdf([]), "escaneado.pdf")

    assert answer.status_code == 422 and answer.json()["code"] == "pdf_without_text"


def test_too_many_files_in_a_minute_wait(
    apis: ApiFactory,
    school: PublicSchool,
    admin_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.reconciliation import router

    monkeypatch.setattr(router, "UPLOADS_PER_MINUTE", 2)
    router.get_upload_limiter.cache_clear()
    try:
        gestao = committed_manager(apis, admin_engine, school)
        account = _account(gestao)
        answers = [_send(gestao, account, b"a;b\nx;y\n", f"n{i}.csv") for i in range(3)]
    finally:
        router.get_upload_limiter.cache_clear()

    assert [a.status_code for a in answers] == [422, 422, 429]
    assert answers[2].json()["code"] == "rate_limited" and "retry-after" in answers[2].headers

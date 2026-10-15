# ruff: noqa: E501  (long assertions)
"""The cash book of a month (CSV and PDF) and the package of the month (ZIP): derived from the ledger,
checked against the summary, safe to open in a spreadsheet, personal data only for the management."""

import csv
import io
import zipfile
from datetime import UTC, date, datetime

import pytest

from app.reports.cash_book import (
    BookRow,
    CashBook,
    PackageTooLarge,
    build_package,
    render_csv,
)
from tests.statement.conftest import Login, Scene
from tests.statement.pdftext import text_of


def _path(school: object, tail: str, period: str | None = "2025-03") -> str:
    base = f"/api/v1/schools/{school}/reports/{tail}"
    return base if period is None else f"{base}?period={period}"


def _rows(content: bytes) -> list[list[str]]:
    assert content.startswith(b"\xef\xbb\xbf")  # the BOM that makes Excel read UTF-8
    return list(csv.reader(io.StringIO(content.decode("utf-8-sig")), delimiter=";"))


def test_the_csv_has_the_opening_every_entry_and_the_closing_of_the_summary(
    scene: Scene, login: Login
) -> None:
    api = login(scene.users["secretaria"])
    summary = api.get(
        f"/api/v1/schools/{scene.fresh.school}/statement/summary", params={"period": "2025-03"}
    ).json()

    response = api.get(_path(scene.fresh.school, "cash-book.csv"))

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert (
        response.headers["content-disposition"] == 'attachment; filename="livro-caixa-2025-03.csv"'
    )
    assert response.headers["cache-control"] == "private, no-store"
    rows = _rows(response.content)
    assert rows[0][:3] == ["Data", "Referência", "Tipo"]
    assert (
        rows[1][3] == "Saldo anterior"
        and rows[1][-1]
        == f"{summary['opening_balance_cents'] // 100},{summary['opening_balance_cents'] % 100:02d}"
    )
    assert rows[-1][3] == "Saldo final"
    closing = summary["closing_balance_cents"]
    assert rows[-1][-1] == f"{closing // 100},{closing % 100:02d}"
    assert len(rows) == 2 + summary["entries_count"] + 1
    assert any("Maria Exemplo" in cell for row in rows for cell in row)


def test_the_pdf_has_the_header_the_balances_and_the_footer(scene: Scene, login: Login) -> None:
    api = login(scene.users["secretaria"])

    response = api.get(_path(scene.fresh.school, "cash-book.pdf"))

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    text = text_of(response.content)
    assert "Livro Caixa" in text and "março de 2025" in text
    assert "Saldo anterior" in text and "Saldo final" in text
    assert "Maria Exemplo" in text


def test_the_package_is_a_zip_with_the_book_in_both_forms(scene: Scene, login: Login) -> None:
    api = login(scene.users["secretaria"])

    response = api.get(_path(scene.fresh.school, "month-package.zip"))

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == 'attachment; filename="pacote-2025-03.zip"'
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert "livro-caixa-2025-03.csv" in names and "livro-caixa-2025-03.pdf" in names
    assert "anexos-faltando.txt" in names  # the scene has rows for files the store never had


def test_a_text_that_looks_like_a_formula_is_shown_never_run() -> None:
    book = CashBook(
        organization_name="APM", school_name="Escola", timezone="America/Sao_Paulo",
        period_start=date(2025, 3, 1), period_end=date(2025, 3, 31),
        generated_at=datetime(2025, 4, 1, tzinfo=UTC), personal_data=True,
        opening_cents=0, closing_cents=-100,
        rows=[BookRow(date(2025, 3, 2), 1, "EXPENSE", '=HYPERLINK("http://x")', "+cmd", "@a", 0, 100, -100)],
    )  # fmt: skip

    cells = [c for row in _rows(render_csv(book)) for c in row]

    assert '\'=HYPERLINK("http://x")' in cells and "'+cmd" in cells and "'@a" in cells
    assert not any(c.startswith(("=", "+", "@")) for c in cells)


def test_the_package_names_are_clean_and_it_has_a_ceiling() -> None:
    package = build_package(
        period="2025-03", csv_bytes=b"a", pdf_bytes=b"b",
        attachments=[(7, "../../etc/passwd nota fiscal.pdf", 3, lambda: b"abc")],
    )  # fmt: skip
    names = zipfile.ZipFile(io.BytesIO(package)).namelist()

    assert "anexos/APM-000007-1-etc_passwd_nota_fiscal.pdf" in names
    with pytest.raises(PackageTooLarge):
        build_package(
            period="2025-03", csv_bytes=b"a", pdf_bytes=b"b",
            attachments=[(1, "grande.pdf", 200 * 1024 * 1024, lambda: b"x")],
        )  # fmt: skip


def test_an_employee_gets_neither_the_book_nor_the_package(scene: Scene, login: Login) -> None:
    api = login(scene.users["staff"])

    assert api.get(_path(scene.fresh.school, "cash-book.csv")).status_code == 403
    assert api.get(_path(scene.fresh.school, "month-package.zip")).status_code == 403

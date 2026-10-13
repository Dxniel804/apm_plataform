"""The reader of Brazilian receipts, on texts like the ones a model returns: noisy, in capitals,
with the number sometimes on the next line."""

import pytest

from ocr_service.parser import (
    cnpj_is_valid,
    find_cnpj,
    find_date,
    find_total,
    parse_receipt,
    to_cents,
)

VALID_CNPJ = "11.222.333/0001-81"
CUPOM = """PAPELARIA CENTRAL LTDA
CNPJ: 11.222.333/0001-81
RUA DAS FLORES 100 CENTRO
CUPOM FISCAL ELETRONICO - SAT
Data de emissao: 10/09/2026 14:32:10
ITEM CODIGO DESCRICAO QTD VL UNIT VL TOTAL
001 7891234 CANETA AZUL 10 2,50 25,00
002 7895678 PAPEL SULFITE 5 12,40 62,00
SUBTOTAL 87,00
DESCONTO 0,00
VALOR A PAGAR R$ 87,50
DINHEIRO 100,00
TROCO 12,50
Tributos aprox: R$ 9,12
"""


def test_a_whole_receipt() -> None:
    fields = parse_receipt(CUPOM)

    assert fields["total_cents"].value == 8750 and fields["total_cents"].confidence == 0.9
    assert fields["date"].value == "2026-09-10" and fields["date"].confidence == 0.9
    assert (
        fields["document_number"].value == VALID_CNPJ
        and fields["document_number"].confidence == 0.9
    )
    assert (
        fields["merchant"].value == "PAPELARIA CENTRAL LTDA"
        and fields["merchant"].confidence == 0.7
    )


@pytest.mark.parametrize(
    ("token", "cents"),
    [
        ("87,50", 8750),
        ("1.234,56", 123456),
        ("0,99", 99),
        ("87.50", 8750),
        ("12.345.678,90", 1234567890),
        ("87,5", None),
        ("87", None),
        ("abc", None),
        ("1,234,56", None),
    ],
)
def test_amounts_in_the_brazilian_way(token: str, cents: int | None) -> None:
    assert to_cents(token) == cents


@pytest.mark.parametrize(
    ("text", "cents", "confidence"),
    [
        ("VALOR TOTAL R$ 1.234,56", 123456, 0.9),
        ("VALOR A PAGAR\n87,50", 8750, 0.9),  # the number on the next line
        ("TOTAL A PAGAR: 40,00", 4000, 0.9),
        ("TOTAL R$ 15,90", 1590, 0.8),
        ("Total   15,90\nDinheiro 20,00\nTroco 4,10", 1590, 0.8),
        ("TOTAL GERAL 100,00\nVALOR TOTAL 90,00", 10000, 0.9),
    ],
)
def test_the_total_is_the_one_next_to_its_label(text: str, cents: int, confidence: float) -> None:
    total = find_total(text)

    assert total is not None and (total.value, total.confidence) == (cents, confidence)


def test_a_label_wins_over_a_bigger_number_and_the_change_is_never_the_total() -> None:
    text = "ITEM 1 500,00\nTROCO 12,50\nSUBTOTAL 90,00\nVALOR A PAGAR 87,50\nDINHEIRO 600,00"

    total = find_total(text)

    assert total is not None and total.value == 8750


def test_without_a_label_the_largest_amount_is_a_weak_guess() -> None:
    total = find_total("ARROZ 5,00\nFEIJAO 7,50\nCAFE 12,30")

    assert total is not None and (total.value, total.confidence) == (1230, 0.4)


@pytest.mark.parametrize(
    "text", ["", "sem numeros", "TOTAL", "R$ 0,00", "TOTAL 0,00", "TROCO 5,00"]
)
def test_no_amount_no_total(text: str) -> None:
    assert find_total(text) is None


@pytest.mark.parametrize(
    ("text", "iso", "confidence"),
    [
        ("EMISSAO: 10/09/2026 14:32", "2026-09-10", 0.9),
        ("Data 05/01/26", "2026-01-05", 0.9),
        ("10-09-2026", "2026-09-10", 0.7),
        ("10.09.2026\n10/09/2026", "2026-09-10", 0.7),
        ("10/09/2026 e 11/09/2026", "2026-09-10", 0.5),
    ],
)
def test_the_date(text: str, iso: str, confidence: float) -> None:
    found = find_date(text)

    assert found is not None and (found.value, found.confidence) == (iso, confidence)


@pytest.mark.parametrize(
    "text", ["", "31/02/2026", "99/99/2026", "1/2/3", "12345678", "13/13/2026"]
)
def test_an_impossible_date_is_not_a_date(text: str) -> None:
    assert find_date(text) is None


def test_the_labelled_date_beats_an_earlier_one() -> None:
    found = find_date("VALIDADE 01/01/2030\nEMISSAO 10/09/2026")

    assert found is not None and found.value == "2026-09-10"


@pytest.mark.parametrize(
    ("digits", "valid"),
    [
        ("11222333000181", True),
        ("11222333000182", False),
        ("00000000000000", False),
        ("1122233300018", False),
        ("abcdefghijklmn", False),
    ],
)
def test_the_check_digits_of_a_cnpj(digits: str, valid: bool) -> None:
    assert cnpj_is_valid(digits) is valid


def test_a_cnpj_without_punctuation_is_found_and_formatted() -> None:
    found, line = find_cnpj("LOJA\nCNPJ 11222333000181\n")

    assert found is not None and found.value == VALID_CNPJ and line == 1


def test_fourteen_digits_that_are_not_a_cnpj_are_not_reported() -> None:
    assert find_cnpj("CODIGO DE BARRAS 12345678901234")[0] is None


def test_a_labelled_cnpj_with_a_wrong_digit_is_kept_with_low_confidence() -> None:
    found, _ = find_cnpj("CNPJ: 11.222.333/0001-82")

    assert found is not None and found.confidence == 0.4


def test_the_shop_is_the_line_above_the_cnpj_not_the_noise() -> None:
    text = "CUPOM FISCAL ELETRONICO\nMERCADO BOM PRECO LTDA\nCNPJ 11.222.333/0001-81\nRUA A, 10"

    fields = parse_receipt(text)

    assert fields["merchant"].value == "MERCADO BOM PRECO LTDA"


def test_the_shop_on_the_same_line_as_the_cnpj() -> None:
    fields = parse_receipt("PADARIA DO ZE CNPJ 11.222.333/0001-81")

    assert fields["merchant"].value == "PADARIA DO ZE"


def test_without_a_cnpj_the_first_clean_line_is_a_guess() -> None:
    fields = parse_receipt("12/34\nLIVRARIA ESTRELA\nTOTAL 10,00")

    assert fields["merchant"].value == "LIVRARIA ESTRELA" and fields["merchant"].confidence == 0.5


def test_a_page_with_nothing_readable_gives_nothing() -> None:
    assert parse_receipt("") == {}
    assert parse_receipt("@@@ ### ///") == {}
    assert parse_receipt("   \n\n  \t ") == {}


def test_a_recibo_with_only_an_amount_and_a_date() -> None:
    fields = parse_receipt("RECIBO\nRecebi de Maria a quantia de\nR$ 150,00\n05/10/2026")

    assert fields["date"].value == "2026-10-05"
    assert fields["total_cents"].value == 15000 and fields["total_cents"].confidence == 0.4
    assert "merchant" not in fields  # "RECIBO" is noise, not a shop

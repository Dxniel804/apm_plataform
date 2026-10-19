# ruff: noqa: E501  (long lines of a PDF)
"""The other two official forms of the FNDE: "Relação de bens adquiridos ou produzidos" and "Conciliação bancária".

Same rules as the Demonstrativo (app/pdde/forms.py): the layout of the FNDE is drawn again, the numbers
are sums of what the school classified, and what the data cannot fill is left blank and listed at the top.

* The list of goods has only goods of CAPITAL (the instructions of the form), one row per document.
* The bank reconciliation is for ONE account of the PDDE. What is typed on it by hand (the credits and the
  debits that are not on the statement, the unpaid invoices) is NOT guessed: the lines are blank. Next to it,
  and outside the form, the system shows a conference: the balance of the statement against what the
  forms add up to, so a person sees at once whether something is missing.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.platypus import Flowable, KeepTogether, Paragraph, Spacer, Table, TableStyle

from app.pdde import forms
from app.pdde.report import program_name
from app.pdde.schemas import LineOut
from app.reports.format import brl, local_date, printable
from app.reports.layout import BAND, INK, MARGIN, build_pdf, para

CONTENT = A4[0] - 2 * MARGIN  # portrait
_BOX = forms._BOX


# --- Relação de bens ----------------------------------------------------------------------------


@dataclass
class GoodsRow:
    doc_type: str
    doc_number: str
    doc_date: str
    specification: str
    quantity: int | None
    unit_cents: int | None
    total_cents: int


@dataclass
class Goods:
    program_label: str
    year: int
    entity: dict[str, str] | None
    fallback_name: str
    rows: list[GoodsRow]
    notices: list[str] = field(default_factory=list)


def build_goods(
    *,
    lines: list[LineOut],
    program: str,
    label: str | None,
    year: int,
    entity: dict[str, str] | None,
    fallback_name: str,
) -> Goods:
    rows: list[GoodsRow] = []
    without_quantity = 0
    without_document = 0
    inexact = 0
    for ln in sorted(
        (x for x in lines if forms._same(x, program, label)),
        key=lambda x: (x.posted_on, str(x.line_id)),
    ):
        c = ln.classification
        if c is None or c.kind != "EXPENSE" or c.economic_category != "CAPITAL":
            continue
        docs = [d for d in ln.documents if not d.voided]
        if not docs:
            without_document += 1
            rows.append(GoodsRow("", "", "", c.object or "", None, None, abs(ln.amount_cents)))
            continue
        for d in docs:
            unit = None
            if d.quantity:
                if d.amount_cents % d.quantity == 0:
                    unit = d.amount_cents // d.quantity
                else:
                    inexact += 1
            else:
                without_quantity += 1
            rows.append(
                GoodsRow(
                    forms.DOC_ABBREVIATION[d.doc_kind],
                    d.doc_number or "",
                    local_date(d.issued_on),
                    d.specification or c.object or "",
                    d.quantity,
                    unit,
                    d.amount_cents,
                )  # fmt: skip
            )
    notices: list[str] = []
    if entity is None:
        notices.append(
            "Faltam os dados da entidade (nome no CNPJ, CNPJ, endereço, município e UF): campos 03 a 07."
        )
    if not rows:
        notices.append(
            "Nenhuma despesa de capital classificada neste programa e ano: não há bens a relacionar."
        )
    if without_document:
        notices.append(
            f"{without_document} despesa(s) de capital sem documento: a linha sai sem tipo, número e data."
        )
    if without_quantity:
        notices.append(
            f"{without_quantity} documento(s) sem quantidade: informe a quantidade e o que é o bem."
        )
    if inexact:
        notices.append(
            f"{inexact} documento(s) cujo valor não divide pela quantidade: o valor unitário ficou em branco."
        )
    return Goods(program_name(program, label), year, entity, fallback_name, rows, notices)


def _notices(notices: list[str]) -> list[Flowable]:
    if not notices:
        return []
    return [
        para("CONFERIR ANTES DE ASSINAR:", "notice"),
        *[para(f"• {n}", "notice") for n in notices],
        Spacer(1, 6),
    ]


def render_goods(g: Goods, *, generated_at: datetime, place: str) -> bytes:
    h = _h
    head = [
        [
            h("08 – Documento"),
            "",
            "",
            h("09 – Especificação dos bens"),
            h("10 – Quantidade"),
            h("11 – Valor (R$)"),
            "",
        ],
        [h("Tipo"), h("Número"), h("Data"), "", "", h("Unitário"), h("Total")],
    ]
    body = [
        [
            para(r.doc_type, "cell"), para(r.doc_number, "cell"), para(r.doc_date, "cell"), para(r.specification, "cell"),
            para("" if r.quantity is None else str(r.quantity), "cell_right"),
            para("" if r.unit_cents is None else brl(r.unit_cents), "cell_right"), para(brl(r.total_cents), "cell_right"),
        ]
        for r in g.rows
    ]  # fmt: skip
    total = [
        para("12 – TOTAL", "cell_bold"),
        *[""] * 5,
        para(brl(sum(r.total_cents for r in g.rows)), "cell_bold_right"),
    ]
    cells = [*head, *body, total]
    widths = [CONTENT * x for x in (0.07, 0.11, 0.13, 0.29, 0.12, 0.13, 0.15)]
    table = Table(cells, colWidths=widths, repeatRows=2)
    last = len(cells) - 1
    style: list[Any] = [
        *_BOX, ("BACKGROUND", (0, 0), (-1, 1), BAND), ("SPAN", (0, 0), (2, 0)), ("SPAN", (5, 0), (6, 0)),
        ("SPAN", (0, last), (5, last)), ("BACKGROUND", (0, last), (-1, last), BAND), ("LINEABOVE", (0, last), (-1, last), 0.8, INK),
    ]  # fmt: skip
    for col in (3, 4):
        style.append(("SPAN", (col, 0), (col, 1)))
    table.setStyle(TableStyle(style))
    story: list[Flowable] = [
        para("PRESTAÇÃO DE CONTAS", "title"),
        para("RELAÇÃO DE BENS ADQUIRIDOS OU PRODUZIDOS", "subtitle"),
        para("Modelo de formulário do FNDE, preenchido pelo APM Digital: só bens de capital, um por documento.", "small"),
        Spacer(1, 8),
        *_notices(g.notices),
        forms._block("BLOCO 1 – IDENTIFICAÇÃO", CONTENT),
        _identification(g.program_label, g.year, g.entity, g.fallback_name),
        Spacer(1, 6),
        forms._block("BLOCO 2 – IDENTIFICAÇÃO DOS BENS ADQUIRIDOS OU PRODUZIDOS", CONTENT),
        table,
        Spacer(1, 10),
        KeepTogether(forms.signature_block("BLOCO 3 – AUTENTICAÇÃO", place, generated_at.date(), "do representante legal da Unidade Executora Própria", CONTENT)),
    ]  # fmt: skip
    return build_pdf(
        story,
        title=f"Relação de bens {g.program_label} {g.year}",
        header=printable(f"{g.program_label} · exercício {g.year}"),
        footer_code=f"relação de bens pdde {g.year}",
        footer_note="Gerado pelo APM Digital; a prestação oficial é feita no sistema do banco e junto à prefeitura.",
    )


def _identification(
    program_label: str, year: int, entity: dict[str, str] | None, fallback_name: str
) -> Table:
    return forms.identification_table(program_label, year, entity, fallback_name, width=CONTENT)


def _h(text: str) -> Paragraph:
    return para(text, "small")


# --- Conciliação bancária -----------------------------------------------------------------------


@dataclass
class Reconciliation:
    year: int
    entity: dict[str, str] | None
    fallback_name: str
    bank_name: str
    account_last4: str | None
    statement_date: date | None
    statement_cents: int | None
    # the conference of the system (outside the form): None when it cannot be made
    applied_cents: int | None
    unclassified_cents: int
    other_cents: int
    notices: list[str] = field(default_factory=list)


def build_reconciliation(
    *,
    lines: list[LineOut],
    account_id: Any,
    year: int,
    bank_name: str,
    account_last4: str | None,
    statement_date: date | None,
    statement_cents: int | None,
    program_balance_sum: int | None,
    entity: dict[str, str] | None,
    fallback_name: str,
) -> Reconciliation:
    mine = [ln for ln in lines if ln.account_id == account_id]
    unclassified = sum(ln.amount_cents for ln in mine if ln.classification is None)
    other = sum(
        ln.amount_cents
        for ln in mine
        if ln.classification is not None
        and ln.classification.kind in ("TAX_TO_EEX", "REFUND", "INELIGIBLE")
    )
    notices: list[str] = []
    if entity is None:
        notices.append(
            "Faltam os dados da entidade (nome no CNPJ, CNPJ, endereço, município e UF): campos 03 a 07."
        )
    if statement_cents is None:
        notices.append(
            "Nenhum extrato desta conta com saldo foi importado até 31/12: o campo 11 está em branco."
        )
    elif statement_date is not None and statement_date < date(year, 12, 31):
        notices.append(
            f"O último extrato importado vai só até {local_date(statement_date)}: importe o de dezembro para o saldo de 31/12."
        )
    notices.append(
        "Agência e número da conta não ficam no sistema (só os últimos dígitos): escreva-os à mão nos campos 09 e 10."
    )
    notices.append(
        "Os campos 12 a 16 não são preenchidos pelo sistema: lance à mão o que não aparece no extrato (rendimentos creditados depois, cheques não compensados, notas recebidas e não pagas)."
    )
    return Reconciliation(
        year,
        entity,
        fallback_name,
        bank_name,
        account_last4,
        statement_date,
        statement_cents,
        program_balance_sum,
        unclassified,
        other,
        notices,
    )


def render_reconciliation(r: Reconciliation, *, generated_at: datetime, place: str) -> bytes:
    h = _h
    bank = Table(
        [
            [forms._field("08", "Banco", r.bank_name), forms._field("09", "Cód. da agência", ""), forms._field("10", "Nº da conta corrente", f"final {r.account_last4}" if r.account_last4 else ""), forms._field("11", "Saldo do extrato bancário", f"{local_date(r.statement_date) if r.statement_date else '__/__/____'}   {brl(r.statement_cents) if r.statement_cents is not None else 'R$ __________'}")],
        ],
        colWidths=[CONTENT * 0.22, CONTENT * 0.18, CONTENT * 0.2, CONTENT * 0.4],
    )  # fmt: skip
    bank.setStyle(TableStyle(_BOX))
    rows = [
        [
            h("12 – Créditos não demonstrados no extrato"),
            "",
            h("13 – Débitos não demonstrados no extrato"),
            "",
            h("14 – Restos a pagar processados"),
            "",
        ],
        [h("Histórico"), h("Valor (R$)")] * 3,
    ]
    rows += [[para(" ", "cell") for _ in range(6)] for _ in range(6)]
    rows.append(
        [
            para("16 – Total", "cell_bold"),
            para(" ", "cell"),
            para("16 – Total", "cell_bold"),
            para(" ", "cell"),
            para("16 – Total", "cell_bold"),
            para(" ", "cell"),
        ]
    )
    widths = [CONTENT * x for x in (0.20, 0.13, 0.20, 0.13, 0.21, 0.13)]
    demo = Table(rows, colWidths=widths, rowHeights=[None, None, *[20] * 6, None])
    demo.setStyle(
        TableStyle(
            [
                *_BOX,
                ("BACKGROUND", (0, 0), (-1, 1), BAND),
                ("SPAN", (0, 0), (1, 0)),
                ("SPAN", (2, 0), (3, 0)),
                ("SPAN", (4, 0), (5, 0)),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, INK),
            ]
        )
    )
    balance = Table(
        [
            [
                forms._field(
                    "15", "Saldo contábil  (11 + 12) – (13 + 14)", "R$ ______________________"
                )
            ]
        ],
        colWidths=[CONTENT],
    )
    balance.setStyle(TableStyle(_BOX))
    story: list[Flowable] = [
        para("PRESTAÇÃO DE CONTAS", "title"),
        para("CONCILIAÇÃO BANCÁRIA", "subtitle"),
        para("Modelo de formulário do FNDE, preenchido pelo APM Digital com o saldo do extrato. Uma conta do PDDE por formulário.", "small"),
        Spacer(1, 8),
        *_notices(r.notices),
        forms._block("BLOCO 1 – IDENTIFICAÇÃO", CONTENT),
        _identification("PDDE (todos os programas desta conta)", r.year, r.entity, r.fallback_name),
        Spacer(1, 6),
        forms._block("BLOCO 2 – IDENTIFICAÇÃO BANCÁRIA E SALDO", CONTENT),
        bank,
        Spacer(1, 6),
        forms._block("BLOCO 3 – DEMONSTRAÇÃO CONTÁBIL / FINANCEIRA", CONTENT),
        demo,
        Spacer(1, 4),
        balance,
        Spacer(1, 10),
        KeepTogether(forms.signature_block("BLOCO 4 – AUTENTICAÇÃO", place, generated_at.date(), "do representante legal da entidade", CONTENT)),
        Spacer(1, 14),
        *_conference(r),
    ]  # fmt: skip
    return build_pdf(
        story,
        title=f"Conciliação bancária {r.year}",
        header=printable(f"PDDE · conciliação bancária · exercício {r.year}"),
        footer_code=f"conciliação bancária pdde {r.year}",
        footer_note="Gerado pelo APM Digital; a prestação oficial é feita no sistema do banco e junto à prefeitura.",
    )


def _conference(r: Reconciliation) -> list[Flowable]:
    """Outside the form: the statement against what the forms of the programs add up to."""
    rows: list[list[Any]] = [
        [para("CONFERÊNCIA DO SISTEMA (não faz parte do formulário)", "cell_bold"), ""]
    ]
    if r.statement_cents is None or r.applied_cents is None:
        rows.append(
            [
                para(
                    "Não foi possível conferir: falta o saldo do extrato, ou a escola tem mais de uma conta do PDDE (o saldo do ano anterior é por programa, não por conta).",
                    "small",
                ),
                "",
            ]
        )
    else:
        explained = r.applied_cents + r.unclassified_cents + r.other_cents
        difference = r.statement_cents - explained
        rows += [
            [
                para("Saldo do extrato (campo 11)", "cell"),
                para(brl(r.statement_cents), "cell_right"),
            ],
            [
                para("Saldo dos programas (soma dos campos 15 dos formulários)", "cell"),
                para(brl(r.applied_cents), "cell_right"),
            ],
            [
                para("Lançamentos ainda sem classificação (líquido)", "cell"),
                para(brl(r.unclassified_cents), "cell_right"),
            ],
            [
                para("Imposto à prefeitura, estorno e despesa não elegível (líquido)", "cell"),
                para(brl(r.other_cents), "cell_right"),
            ],
            [
                para("Diferença (extrato – o resto)", "cell_bold"),
                para(brl(difference), "cell_bold_right"),
            ],
            [
                para(
                    "Bate."
                    if difference == 0
                    else "Não bate: confira o saldo do ano anterior, rendimentos e tarifas ainda não lançados e lançamentos sem classificação.",
                    "small",
                ),
                "",
            ],
        ]
    table = Table(rows, colWidths=[CONTENT * 0.75, CONTENT * 0.25])
    table.setStyle(
        TableStyle(
            [*_BOX, ("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), BAND)]
            + (
                [("SPAN", (0, 1), (-1, 1))]
                if len(rows) == 2
                else [("SPAN", (0, len(rows) - 1), (-1, len(rows) - 1))]
            )
        )
    )
    return [KeepTogether([table])]

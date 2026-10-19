# ruff: noqa: E501  (long lines of a PDF)
"""The official FNDE form "Demonstrativo da execução da receita e da despesa e de pagamentos efetuados",
filled from what the school typed in the PDDE layer.

The layout follows the form of the FNDE (the four blocks and the numbering of the fields 01 to 28), one form
per program and year. NOTHING here is a new rule: every number is a sum of the lines the school classified,
and what the data cannot fill is left blank and listed in the notice at the top, so a person never signs
a form that looks complete and is not. The form of the FNDE (a .doc file) is not copied: the layout is drawn
again.
"""

from dataclasses import dataclass, field
from datetime import date, datetime

from reportlab.lib.pagesizes import A4
from reportlab.platypus import Flowable, KeepTogether, Paragraph, Spacer, Table, TableStyle

from app.pdde import tax_id
from app.pdde.report import program_name
from app.pdde.schemas import LineOut
from app.reports.format import brl, local_date, printable
from app.reports.layout import BAND, INK, MARGIN, RULE, build_pdf, para

CONTENT = A4[1] - 2 * MARGIN  # landscape

DOC_ABBREVIATION = {"NFE": "NF", "INVOICE": "FT", "RECEIPT": "RB", "OTHER": "DOC"}
SOURCE_NOTE = {
    "typed": "informado pela escola",
    "computed": "calculado dos extratos de anos anteriores",
    "none": "sem lançamentos de anos anteriores (zero)",
}


@dataclass
class Row:
    item: int
    payee: str
    tax_ids: str
    kind: str
    category: str  # "C" (custeio) or "K" (capital)
    doc_types: list[str]
    doc_numbers: list[str]
    doc_dates: list[str]
    payment_number: str
    payment_date: date
    cents: int


@dataclass
class Demonstrativo:
    program_label: str
    year: int
    entity: dict[str, str] | None
    fallback_name: str
    carry: tuple[int, int]
    carry_source: str
    credited: tuple[int, int]
    yielded: tuple[int, int]
    returned: tuple[int, int]
    spent: tuple[int, int]
    period: tuple[date | None, date]
    rows: list[Row]
    notices: list[str] = field(default_factory=list)

    @property
    def revenue(self) -> tuple[int, int]:
        return tuple(  # type: ignore[return-value]
            self.carry[i] + self.credited[i] + self.yielded[i] - self.returned[i] for i in (0, 1)
        )

    @property
    def balance(self) -> tuple[int, int]:
        return (self.revenue[0] - self.spent[0], self.revenue[1] - self.spent[1])


def _same(line: LineOut, program: str, label: str | None) -> bool:
    c = line.classification
    return (
        c is not None and c.program == program and (program != "OUTRO" or c.program_label == label)
    )


def build_demonstrativo(
    *,
    lines: list[LineOut],
    program: str,
    label: str | None,
    year: int,
    carry: dict[tuple[str, str | None], tuple[int, int]],
    carry_source: str,
    entity: dict[str, str] | None,
    fallback_name: str,
) -> Demonstrativo:
    credited, yielded, returned, spent = [0, 0], [0, 0], [0, 0], [0, 0]
    no_category = 0
    rows: list[Row] = []
    first_credit: date | None = None
    first_spend: date | None = None
    notices: list[str] = []
    mine = [ln for ln in lines if _same(ln, program, label)]
    for ln in sorted(mine, key=lambda x: (x.posted_on, str(x.line_id))):
        c = ln.classification
        if c is None:  # pragma: no cover  (mine is filtered by the classification)
            continue
        slot = 1 if c.economic_category == "CAPITAL" else 0
        amount = abs(ln.amount_cents)
        if c.kind == "TRANSFER":
            first_credit = first_credit or ln.posted_on
            if c.economic_category is None:
                no_category += amount
            else:
                credited[slot] += amount
        elif c.kind == "YIELD":
            yielded[slot] += amount
        elif c.kind == "RETURN_TO_FNDE":
            returned[slot] += amount
        elif c.kind == "EXPENSE":
            first_spend = first_spend or ln.posted_on
            spent[slot] += amount
            docs = [d for d in ln.documents if not d.voided]
            payees = list(dict.fromkeys(d.vendor for d in docs))
            ids = list(dict.fromkeys(tax_id.mask(d.vendor_tax_id) for d in docs if d.vendor_tax_id))
            rows.append(
                Row(
                    item=len(rows) + 1,
                    payee=", ".join(payees),
                    tax_ids=", ".join(ids),
                    kind=c.object or "",
                    category="K" if c.economic_category == "CAPITAL" else "C",
                    doc_types=[DOC_ABBREVIATION[d.doc_kind] for d in docs],
                    doc_numbers=[d.doc_number or "" for d in docs],
                    doc_dates=[local_date(d.issued_on) for d in docs],
                    payment_number=c.payment_number or "",
                    payment_date=ln.posted_on,
                    cents=amount,
                )
            )
            if not docs:
                notices.append(
                    f"O pagamento {len(rows)} (R$ {amount / 100:,.2f}) ainda não tem documento.".replace(
                        ",", "X"
                    )
                    .replace(".", ",")
                    .replace("X", ".")
                )
            elif sum(d.amount_cents for d in docs) < amount:
                notices.append(
                    f"Os documentos do pagamento {len(rows)} cobrem só {brl(sum(d.amount_cents for d in docs))} de {brl(amount)}."
                )
            if docs and any(d.vendor_tax_id is None for d in docs):
                notices.append(
                    f"O pagamento {len(rows)} está sem o CNPJ ou CPF do favorecido (campo 21)."
                )
    key = (program, label)
    typed_or_computed = carry.get(key, (0, 0))
    unclassified = sum(1 for ln in lines if ln.classification is None)
    if entity is None:
        notices.append(
            "Faltam os dados da entidade (nome no CNPJ, CNPJ, endereço, município e UF): campos 03 a 07."
        )
    if no_category:
        notices.append(
            f"Há repasses de {brl(no_category)} sem custeio ou capital: não entram nas colunas (campo 09). Classifique-os."
        )
    if unclassified:
        notices.append(
            f"Há {unclassified} lançamento(s) da conta do PDDE sem classificação neste ano; se forem deste programa, faltam aqui."
        )
    if carry_source == "none":
        notices.append(
            "O saldo do ano anterior (campo 08) está em zero: informe-o se a escola já tinha saldo."
        )
    elif carry_source == "computed":
        notices.append(
            "O saldo do ano anterior (campo 08) foi calculado dos extratos anteriores: confira com a prestação do ano passado."
        )
    # Field 17: from the first credit if nothing was carried, else from the first expense (instructions of the form).
    started = first_credit if sum(typed_or_computed) == 0 else first_spend
    return Demonstrativo(
        program_label=program_name(program, label),
        year=year,
        entity=entity,
        fallback_name=fallback_name,
        carry=typed_or_computed,
        carry_source=carry_source,
        credited=(credited[0], credited[1]),
        yielded=(yielded[0], yielded[1]),
        returned=(returned[0], returned[1]),
        spent=(spent[0], spent[1]),
        period=(started, date(year, 12, 31)),
        rows=rows,
        notices=notices,
    )


# --- the page ------------------------------------------------------------------------------------

_BOX = [
    ("BOX", (0, 0), (-1, -1), 0.5, RULE),
    ("INNERGRID", (0, 0), (-1, -1), 0.4, RULE),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
]


def _field(number: str, label: str, value: str = "") -> list[Flowable]:
    return [para(f"{number} – {label}", "small"), para(value or " ", "cell_bold")]


def _block(title: str, width: float = CONTENT) -> Table:
    """The heading of a block: plain bold text over a thin line (no coloured bar), with room above."""
    table = Table([[para(title, "cell_bold")]], colWidths=[width])
    table.keepWithNext = True  # a heading never stays alone at the end of a page
    table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.8, INK),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _identification(d: Demonstrativo) -> Table:
    return identification_table(d.program_label, d.year, d.entity, d.fallback_name)


def identification_table(
    program_label: str,
    year: int,
    e: dict[str, str] | None,
    fallback_name: str,
    width: float = CONTENT,
) -> Table:
    """Block 1 of the three forms: fields 01 to 07."""
    name = e["legal_name"] if e else fallback_name
    cells = [
        [
            _field("01", "Programa/Ação", program_label),
            _field("02", "Exercício", str(year)),
            "",
            "",
        ],
        [
            _field("03", "Nome", name),
            "",
            _field("04", "Número do CNPJ", tax_id.mask(e["cnpj"]) if e else ""),
            "",
        ],
        [
            _field("05", "Endereço", e["address"] if e else ""),
            _field("06", "Município", e["city"] if e else ""),
            _field("07", "UF", e["state"] if e else ""),
            "",
        ],
    ]
    w = width
    table = Table(cells, colWidths=[w * 0.40, w * 0.25, w * 0.20, w * 0.15])
    table.setStyle(
        TableStyle(
            [
                *_BOX,
                ("SPAN", (1, 0), (3, 0)),
                ("SPAN", (0, 1), (1, 1)),
                ("SPAN", (2, 1), (3, 1)),
                ("SPAN", (2, 2), (3, 2)),
            ]
        )
    )
    return table


def _group_table(
    groups: list[tuple[str, str, tuple[int, int]]], extra: list[tuple[str, str]] | None = None
) -> Table:
    """Groups of (number, label, (custeio, capital)): two columns each, as in the form, and, at the end, fields
    that take two columns and one value (17 and 18)."""
    head: list[object] = []
    sub: list[object] = []
    val: list[object] = []
    for number, label, values in groups:
        head += [para(f"{number} – {label}", "small"), ""]
        sub += [para("Custeio", "small"), para("Capital", "small")]
        val += [para(brl(values[0]), "cell_bold_right"), para(brl(values[1]), "cell_bold_right")]
    for label, value in extra or []:
        head += [para(label, "small"), ""]
        sub += [para(" ", "small"), ""]
        val += [para(value, "cell_bold"), ""]
    columns = len(head)
    w = CONTENT / columns
    table = Table([head, sub, val], colWidths=[w] * columns)
    style: list[tuple] = [*_BOX, ("BACKGROUND", (0, 0), (-1, 1), BAND)]  # type: ignore[type-arg]
    for col in range(0, columns, 2):
        style.append(("SPAN", (col, 0), (col + 1, 0)))
    for col in range(len(groups) * 2, columns, 2):
        style += [("SPAN", (col, 1), (col + 1, 1)), ("SPAN", (col, 2), (col + 1, 2))]
    table.setStyle(TableStyle(style))
    return table


def _summary(d: Demonstrativo) -> list[Flowable]:
    top = [
        ("08", "Saldo reprogramado do exercício anterior", d.carry),
        ("09", "Valor creditado pelo FNDE no exercício", d.credited),
        ("10", "Recursos próprios", (0, 0)),
        ("11", "Rendimento de aplicação financeira", d.yielded),
        ("12", "Devolução de recursos ao FNDE (–)", d.returned),
    ]
    bottom = [
        ("13", "Valor total da receita", d.revenue),
        ("14", "Valor da despesa realizada (–)", d.spent),
        ("15", "Saldo a reprogramar para o exercício seguinte", d.balance),
        ("16", "Saldo devolvido", (0, 0)),
    ]
    start = local_date(d.period[0]) if d.period[0] else "___/___/___"
    period = f"{start} a {local_date(d.period[1])}"
    return [
        _group_table(top),
        _group_table(
            bottom, [("17 – Período de execução", period), ("18 – Nº de escolas atendidas", "1")]
        ),
    ]


def _payments(d: Demonstrativo) -> Table:
    def h(text: str) -> Paragraph:
        return para(text, "small")

    head = [
        [
            h("19 – Item"),
            h("20 – Nome do favorecido"),
            h("21 – CNPJ ou CPF"),
            h("22 – Tipo de bens e materiais adquiridos ou serviços contratados"),
            h("23 – Origem R$"),
            h("24 – Nat. desp."),
            h("25 – Documento"),
            "",
            "",
            h("26 – Pagamento"),
            "",
            h("27 – Valor (R$)"),
        ],
        ["", "", "", "", "", "", h("Tipo"), h("Número"), h("Data"), h("Nº Ch/OB"), h("Data"), ""],
    ]
    body: list[list[object]] = []
    for r in d.rows:
        body.append(
            [
                para(str(r.item), "cell"),
                para(r.payee, "cell"),
                para(r.tax_ids, "cell"),
                para(r.kind, "cell"),
                para("FNDE", "cell"),
                para(r.category, "cell"),
                para(" / ".join(r.doc_types), "cell"),
                para(" / ".join(r.doc_numbers), "cell"),
                para(" / ".join(r.doc_dates), "cell"),
                para(r.payment_number, "cell"),
                para(local_date(r.payment_date), "cell"),
                para(brl(r.cents), "cell_right"),
            ]
        )
    total = [
        para("28 – TOTAL", "cell_bold"),
        *[""] * 10,
        para(brl(sum(r.cents for r in d.rows)), "cell_bold_right"),
    ]
    cells = [*head, *body, total]
    w = CONTENT
    widths = [
        w * x for x in (0.04, 0.16, 0.12, 0.16, 0.05, 0.04, 0.05, 0.07, 0.09, 0.07, 0.07, 0.08)
    ]
    widths[-1] = w - sum(widths[:-1])
    table = Table(cells, colWidths=widths, repeatRows=2)
    last = len(cells) - 1
    style = [
        *_BOX,
        ("SPAN", (6, 0), (8, 0)),
        ("SPAN", (9, 0), (10, 0)),
        ("BACKGROUND", (0, 0), (-1, 1), BAND),
        ("SPAN", (0, last), (10, last)),
        ("BACKGROUND", (0, last), (-1, last), BAND),
    ]
    for col in (0, 1, 2, 3, 4, 5, 11):
        style.append(("SPAN", (col, 0), (col, 1)))
    table.setStyle(TableStyle(style))
    return table


def signature_block(
    title: str, place: str, today: date, who: str, width: float = CONTENT
) -> list[Flowable]:
    """The authentication block: place and date, the legible name and the signature."""
    sign = Table(
        [
            [
                para(f"{place or '_______________'}, {local_date(today)}", "cell"),
                para("_______________________________", "cell"),
                para("_______________________________", "cell"),
            ],
            [
                para("Local e data", "small"),
                para(f"Nome legível do(a) dirigente ou {who}", "small"),
                para(f"Assinatura do(a) dirigente ou {who}", "small"),
            ],
        ],
        colWidths=[width * 0.28, width * 0.36, width * 0.36],
    )
    sign.setStyle(
        TableStyle([("TOPPADDING", (0, 0), (-1, 0), 26), ("LEFTPADDING", (0, 0), (-1, -1), 0)])
    )
    return [_block(title, width), sign]


def render_pdf(d: Demonstrativo, *, generated_at: datetime, place: str) -> bytes:
    story: list[Flowable] = [
        para("PRESTAÇÃO DE CONTAS", "title"),
        para(
            "DEMONSTRATIVO DA EXECUÇÃO DA RECEITA E DA DESPESA E DE PAGAMENTOS EFETUADOS",
            "subtitle",
        ),
        para(
            "Modelo de formulário do FNDE (Resolução CD/FNDE nº 15/2021, art. 33), preenchido pelo APM Digital a partir dos lançamentos classificados. Um formulário por programa.",
            "small",
        ),
        Spacer(1, 8),
    ]
    if d.notices:
        story.append(para("CONFERIR ANTES DE ASSINAR:", "notice"))
        story.extend(para(f"• {n}", "notice") for n in d.notices)
        story.append(Spacer(1, 6))
    story += [
        _block("BLOCO 1 – IDENTIFICAÇÃO"),
        _identification(d),
        Spacer(1, 6),
        _block("BLOCO 2 – SÍNTESE DA EXECUÇÃO DA RECEITA E DA DESPESA (R$)"),
        *_summary(d),
        Spacer(1, 3),
        para(f"Saldo do ano anterior (campo 08): {SOURCE_NOTE[d.carry_source]}.", "small"),
        Spacer(1, 6),
        _block("BLOCO 3 – PAGAMENTOS EFETUADOS"),
        _payments(d),
        Spacer(1, 10),
    ]
    sign = signature_block(
        "BLOCO 4 – AUTENTICAÇÃO", place, generated_at.date(), "do representante legal"
    )
    story.append(KeepTogether(sign))
    return build_pdf(
        story,
        title=f"Demonstrativo {d.program_label} {d.year}",
        header=printable(f"{d.program_label} · exercício {d.year}"),
        footer_code=f"demonstrativo pdde {d.year}",
        footer_note="Gerado pelo APM Digital; a prestação oficial é feita no sistema do banco e junto à prefeitura.",
        landscape_page=True,
    )

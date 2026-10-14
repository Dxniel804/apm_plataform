"""The PDF of one campaign: what it collected, what it cost, what each product sold and every order
with its payment and its delivery.

Drawn with the pieces of `app.reports.layout` (the same page and footer as the other reports). The
figures are the ones of `orders.dashboard`: nothing is recomputed here. The cost is a management
metric and the PDF says so; it is not a ledger entry.
"""

from datetime import datetime

from reportlab.platypus import Flowable, Paragraph, Spacer

from app.campaigns.schemas import CampaignDashboard, OrderOut
from app.reports.format import brl, local_datetime, reference
from app.reports.layout import (
    STYLES,
    Column,
    build_pdf,
    data_table,
    identification_table,
    key_value_table,
    para,
)

STATUS_LABELS = {"DRAFT": "Rascunho", "ACTIVE": "À venda", "ENDED": "Encerrada"}
PAYMENT_LABELS = {"PAID": "Aprovado", "PENDING": "Pendente", "CANCELLED": "Cancelado"}
DELIVERY_LABELS = {"DELIVERED": "Entregue", "PENDING": "A entregar"}
MAX_ORDERS_IN_PDF = 5000


def _who(order: OrderOut) -> str:
    parts = [part for part in (order.student_name, order.class_name) if part]
    return " · ".join(parts) if parts else "—"


def _items(order: OrderOut) -> str:
    return "; ".join(f"{line.quantity} × {line.item_name}" for line in order.lines) or "—"


def render_campaign_report(
    *,
    organization_name: str,
    school_name: str,
    timezone: str,
    generated_at: datetime,
    dashboard: CampaignDashboard,
    orders: list[OrderOut],
) -> bytes:
    story: list[Flowable] = [
        para("Relatório da campanha", "title"),
        para(dashboard.title, "subtitle"),
        Spacer(1, 6),
        identification_table(
            [
                ("Organização", organization_name),
                ("Escola", school_name),
                ("Situação", STATUS_LABELS[dashboard.status]),
                ("Gerado em", local_datetime(generated_at, timezone)),
            ]
        ),
        Paragraph("Resumo", STYLES["h2"]),
    ]
    rows: list[tuple[str, str, str]] = [
        ("Pedidos aprovados", str(dashboard.paid_orders_count), "normal"),
        ("Pedidos pendentes", str(dashboard.pending_orders_count), "sub"),
        ("Pedidos cancelados", str(dashboard.cancelled_orders_count), "sub"),
        ("Unidades vendidas (pedidos aprovados)", str(dashboard.units_sold), "normal"),
        ("Pedidos entregues", str(dashboard.delivered_orders_count), "normal"),
        ("Pedidos a entregar", str(dashboard.to_deliver_orders_count), "normal"),
        ("Arrecadado", brl(dashboard.collected_cents), "medium"),
    ]
    if dashboard.cost_complete:
        rows.append(("Custos", brl(dashboard.cost_cents), "normal"))
        rows.append(("Lucro", brl(dashboard.profit_cents or 0), "big"))
    else:
        rows.append(("Custos informados", brl(dashboard.cost_cents), "normal"))
        rows.append(("Lucro", "custo não informado", "big"))
    story.append(key_value_table(rows))
    story.append(
        para(
            "O custo é uma medida de gestão da campanha e não é um lançamento no caixa: a saída "
            "de verdade é a despesa registrada.",
            "small",
        )
    )

    story.append(Paragraph("Produtos", STYLES["h2"]))
    story.append(
        data_table(
            [
                Column("Produto", 5),
                Column("Vendidos", 1.4, right=True),
                Column("Arrecadado", 2, right=True),
                Column("Custo", 2, right=True),
            ],
            [
                [
                    item.name,
                    item.units_sold,
                    brl(item.revenue_cents),
                    "—" if item.units_sold and not item.cost_known else brl(item.cost_cents or 0),
                ]
                for item in dashboard.items
            ],
        )
    )

    story.append(Paragraph(f"Pedidos ({len(orders)})", STYLES["h2"]))
    if not orders:
        story.append(para("Nenhum pedido nesta campanha.", "body"))
    else:
        shown = orders[:MAX_ORDERS_IN_PDF]
        story.append(
            data_table(
                [
                    Column("Pedido", 2),
                    Column("Data", 2.2),
                    Column("Responsável", 3),
                    Column("Aluno · turma", 3),
                    Column("Itens", 4),
                    Column("Valor", 1.8, right=True),
                    Column("Pagamento", 1.9),
                    Column("Entrega", 1.8),
                ],
                [
                    [
                        reference(order.reference_code),
                        local_datetime(order.created_at, timezone),
                        order.guardian_name or "—",
                        _who(order),
                        _items(order),
                        brl(order.amount_cents),
                        PAYMENT_LABELS[order.payment_status],
                        DELIVERY_LABELS[order.delivery_status] if order.delivery_status else "—",
                    ]
                    for order in shown
                ],
            )
        )
        if len(orders) > len(shown):
            story.append(para(f"Mostrando os {len(shown)} pedidos mais recentes.", "small"))

    return build_pdf(
        story,
        title=f"Campanha {dashboard.title}",
        header=f"{school_name} · Campanha: {dashboard.title}",
        footer_code=f"Campanha {str(dashboard.campaign_id)[:8]}",
        footer_note="APM Digital. Os custos são medida de gestão, não lançamento no caixa.",
    )

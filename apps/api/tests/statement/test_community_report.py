# ruff: noqa: E501  (long assertions)
"""The one-page report for the community: totals that match the summary, categories and no names."""

from tests.statement.conftest import Login, Scene
from tests.statement.pdftext import pages_of, text_of


def _path(school: object, period: str | None = "2025-03") -> str:
    base = f"/api/v1/schools/{school}/reports/community.pdf"
    return base if period is None else f"{base}?period={period}"


def test_the_report_is_one_page_with_the_totals_of_the_summary_and_no_names(
    scene: Scene, login: Login
) -> None:
    api = login(scene.users["secretaria"])
    summary = api.get(
        f"/api/v1/schools/{scene.fresh.school}/statement/summary", params={"period": "2025-03"}
    ).json()

    response = api.get(_path(scene.fresh.school))

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="prestacao-2025-03.pdf"'
    assert response.headers["cache-control"] == "private, no-store"
    pages = pages_of(response.content)
    assert len(pages) == 1
    text = text_of(response.content)
    assert "Prestação de contas para a comunidade" in text and "março de 2025" in text
    for heading in ("De onde veio o dinheiro", "Em que o dinheiro foi gasto", "Temos agora"):
        assert heading in text
    assert summary["closing_balance_cents"] > 0
    flat = " ".join(text.split())

    def money(cents: int) -> str:
        return f"R$ {cents // 100:,}".replace(",", ".") + f",{cents % 100:02d}"

    assert f"Total {money(summary['total_in_cents'])}" in flat  # the sum of what came in
    assert f"Total {money(summary['total_out_cents'])}" in flat  # the sum of what went out
    for name in ("Maria Exemplo", "João Teste", "Zélia Pintora"):  # people never appear
        assert name not in text


def test_an_employee_does_not_get_it(scene: Scene, login: Login) -> None:
    response = login(scene.users["staff"]).get(_path(scene.fresh.school))

    assert response.status_code == 403

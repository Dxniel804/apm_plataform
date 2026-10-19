# ruff: noqa: E501  (long lines)
"""Tax guides: the retentions on the services the APM pays, and what to type to pay them.

This does NOT decide the law and does NOT talk to the government. A rule (rate, cap, code, due day) is
data the school writes, usually with its accountant, and counts as validated only when somebody says the
accountant confirmed it. A guide is the sum of the retentions of a tax in a month, with the code and the
due date the rule gives, to be typed by hand in the public site of the Receita Federal. Paying it is an
ordinary expense; nothing here touches the ledger."""

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.errors import ProblemError
from app.expenses.access import SchoolScope, not_found
from app.expenses.db_errors import database_rules
from app.statement.periods import month_bounds
from app.tax import calc, repository
from app.tax.repository import Row
from app.tax.schemas import (
    GuideOut,
    MonthOut,
    PreviewOut,
    RetentionIn,
    RetentionOut,
    RuleIn,
    RuleOut,
    RulesOut,
    SuggestionOut,
)

# Where a DARF code is paid (the public Sicalc Web). Confirm the address: governments move sites.
RECEITA_SICALC_URL = "https://sicalc.receita.economia.gov.br/sicalc/principal"

WARNING = (
    "Sugestão de partida, NÃO validada: os números vêm de fontes que não são oficiais e a lei muda. "
    "Confira cada um numa fonte oficial (a lei ou a página do governo) e anote o endereço antes de marcar a regra como conferida."
)
SUGGESTIONS = (
    SuggestionOut(
        rule_key="irrf-servicos-pj",
        label="Imposto de renda retido de serviço profissional de empresa",
        tax_kind="IRRF",
        applies_to="PJ",
        rate_bps=150,
        base_cap_cents=None,
        darf_code="1708",
        howto=None,
        warning=WARNING
        + " Fica por sua conta o vencimento: nenhuma fonte oficial confirmou o dia.",
    ),
    SuggestionOut(
        rule_key="inss-autonomo",
        label="INSS retido de autônomo (pessoa física)",
        tax_kind="INSS",
        applies_to="PF",
        rate_bps=1100,
        base_cap_cents=None,
        darf_code=None,
        howto="Veja no site da Receita como se recolhe o INSS retido: costuma passar pelo eSocial e pela DCTFWeb.",
        warning=WARNING + " O limite (teto) muda todo ano: informe o do ano.",
    ),
    SuggestionOut(
        rule_key="iss-municipal",
        label="ISS retido (prefeitura)",
        tax_kind="ISS",
        applies_to="BOTH",
        rate_bps=None,
        base_cap_cents=None,
        darf_code=None,
        howto="Pague a guia do ISS no site da prefeitura do seu município.",
        warning=WARNING + " A alíquota é do município: procure no site da prefeitura.",
    ),
)


def _rule_out(r: Row) -> RuleOut:
    return RuleOut(
        id=r["id"], rule_key=r["rule_key"], label=r["label"], tax_kind=r["tax_kind"],
        applies_to=r["applies_to"], rate_bps=int(r["rate_bps"]),
        base_cap_cents=None if r["base_cap_cents"] is None else int(r["base_cap_cents"]),
        min_total_cents=int(r["min_total_cents"]), darf_code=r["darf_code"], howto=r["howto"],
        due_day=int(r["due_day"]), due_roll=r["due_roll"], source_note=r["source_note"],
        validated=r["validated_at"] is not None, validated_at=r["validated_at"],
    )  # fmt: skip


def list_rules(db: Session, scope: SchoolScope) -> RulesOut:
    return RulesOut(
        rules=[_rule_out(r) for r in repository.latest_rules(db, scope.school_id)],
        suggestions=list(SUGGESTIONS),
    )


def save_rule(db: Session, scope: SchoolScope, body: RuleIn) -> None:
    """A new row of the rule: the latest counts, and every retention keeps the row it used."""
    with database_rules(db):
        repository.insert_rule(
            db, organization_id=scope.organization_id, school_id=scope.school_id,
            user_id=scope.user_id, values=body.model_dump(exclude={"validated"}), validated=body.validated,
        )  # fmt: skip
        db.commit()


def _rule_for(db: Session, scope: SchoolScope, rule_id: uuid.UUID, provider_kind: str) -> Row:
    rule = repository.rule_by_id(db, scope.school_id, rule_id)
    if rule is None:
        raise not_found()
    if rule["applies_to"] not in ("BOTH", provider_kind):
        raise ProblemError(
            422, "rule_does_not_apply", "This rule does not apply to this kind of provider"
        )
    return rule


def preview(
    db: Session, scope: SchoolScope, rule_id: uuid.UUID, provider_kind: str, gross_cents: int
) -> PreviewOut:
    rule = _rule_for(db, scope, rule_id, provider_kind)
    base, retained = calc.retention(gross_cents, int(rule["rate_bps"]), rule["base_cap_cents"])
    return PreviewOut(
        base_cents=base,
        retained_cents=retained,
        net_cents=gross_cents - retained,
        rate_bps=int(rule["rate_bps"]),
    )


def register(db: Session, scope: SchoolScope, body: RetentionIn) -> uuid.UUID:
    with database_rules(db):
        rule = _rule_for(db, scope, body.rule_id, body.provider_kind)
        base, retained = calc.retention(
            body.gross_cents, int(rule["rate_bps"]), rule["base_cap_cents"]
        )
        new_id = repository.insert_retention(
            db, organization_id=scope.organization_id, school_id=scope.school_id, user_id=scope.user_id,
            rule_id=body.rule_id, provider_kind=body.provider_kind, provider_name=body.provider_name,
            competence=month_bounds(body.competence)[0], gross_cents=body.gross_cents, base_cents=base,
            retained_cents=retained, rate_bps=int(rule["rate_bps"]), note=body.note,
        )  # fmt: skip
        db.commit()
        return new_id


def void(db: Session, scope: SchoolScope, retention_id: uuid.UUID) -> None:
    with database_rules(db):
        if not repository.void_retention(db, scope.school_id, retention_id, scope.user_id):
            raise not_found()
        db.commit()


def _guides(rows: Sequence[Row], competence: dt.date) -> list[GuideOut]:
    """One guide per tax rule and month: the sum of the retentions that are not voided."""
    groups: dict[str, list[Row]] = {}
    for r in rows:
        if not r["voided"]:
            groups.setdefault(r["rule_key"], []).append(r)
    guides: list[GuideOut] = []
    for key in sorted(groups):
        items = groups[key]
        latest = items[
            -1
        ]  # the rows come in the order they were made: the last used the newest version
        total = sum(int(i["retained_cents"]) for i in items)
        guides.append(
            GuideOut(
                rule_key=key,
                label=latest["rule_label"],
                tax_kind=latest["tax_kind"],
                darf_code=latest["darf_code"],
                howto=latest["howto"],
                competence=f"{competence.year:04d}-{competence.month:02d}",
                due_date=calc.due_date(competence, int(latest["due_day"]), latest["due_roll"]),
                total_cents=total,
                count=len(items),
                min_total_cents=int(latest["min_total_cents"]),
                below_minimum=total < int(latest["min_total_cents"]),
                validated=all(bool(i["validated"]) for i in items),
                mixed_versions=len({i["rule_id"] for i in items}) > 1,
                site_url=RECEITA_SICALC_URL if latest["darf_code"] else None,
            )  # fmt: skip
        )
    return guides


def month_view(db: Session, scope: SchoolScope, period: str) -> MonthOut:
    competence = month_bounds(period)[0]
    rows = repository.retentions(db, scope.school_id, competence)
    return MonthOut(
        period=period,
        retentions=[
            RetentionOut(
                id=r["id"],
                rule_key=r["rule_key"],
                rule_label=r["rule_label"],
                provider_kind=r["provider_kind"],
                provider_name=r["provider_name"],
                competence=period,
                gross_cents=int(r["gross_cents"]),
                base_cents=int(r["base_cents"]),
                retained_cents=int(r["retained_cents"]),
                net_cents=int(r["gross_cents"]) - int(r["retained_cents"]),
                rate_bps=int(r["rate_bps"]),
                note=r["note"],
                voided=bool(r["voided"]),
                validated=bool(r["validated"]),
            )  # fmt: skip
            for r in rows
        ],
        guides=_guides(rows, competence),
    )

"""What each expense category is for the PDDE: custeio or capital, and may the PDDE pay it.

The secretaria sees an approved expense with "APM" or "PDDE" already chosen. The choice comes from
here, by the key of the category, and she can change it. The rules are about the law and not about a
school, so they live in code (not in a column the school could edit):

* SUGGESTED: the PDDE usually pays it (material de consumo, pequenos reparos, material permanente).
  It starts as PDDE, and she can change it to APM.
* ALLOWED: the PDDE may pay it, but nothing says it should. It starts as APM.
* FORBIDDEN: the PDDE must not pay it (Res. CD/FNDE 15/2021, art. 4, par. 2: tarifa bancária,
  pessoal, aluguel/telefone/água/luz and tributos that do not fall on the purchase). Always APM.

A key not listed here is ALLOWED, with no nature: the person decides. The list is a proposal, to be
checked against the resolution of each program before a school relies on it.
"""

from typing import Literal

PddeRule = Literal["SUGGESTED", "ALLOWED", "FORBIDDEN"]
Nature = Literal["CUSTEIO", "CAPITAL"]

# key of the category -> (nature, rule)
CATEGORY_RULES: dict[str, tuple[Nature | None, PddeRule]] = {
    # Consumption, pedagogical material, small repairs and permanent goods: what the Básico pays.
    "school_supplies": ("CUSTEIO", "SUGGESTED"),
    "stationery": ("CUSTEIO", "SUGGESTED"),
    "office": ("CUSTEIO", "SUGGESTED"),
    "teaching_material": ("CUSTEIO", "SUGGESTED"),
    "cleaning_supplies": ("CUSTEIO", "SUGGESTED"),
    "maintenance_material": ("CUSTEIO", "SUGGESTED"),
    "equipment_maintenance": ("CUSTEIO", "SUGGESTED"),
    "capital_furniture": ("CAPITAL", "SUGGESTED"),
    "capital_equipment": ("CAPITAL", "SUGGESTED"),
    # Too generic to say: the PDDE may pay it, the secretaria decides (it starts as APM).
    "services": ("CUSTEIO", "ALLOWED"),
    "animals": (None, "ALLOWED"),
    "other_authorized": (None, "ALLOWED"),
    "teacher_reimbursement": (None, "ALLOWED"),
    "director_reimbursement": (None, "ALLOWED"),
    # What the resolution forbids.
    "bank_fees": (None, "FORBIDDEN"),
    "tax_payments": (None, "FORBIDDEN"),
}


def rule_for(key: str) -> tuple[Nature | None, PddeRule]:
    return CATEGORY_RULES.get(key, (None, "ALLOWED"))


def suggested_fund(rule: PddeRule) -> Literal["APM", "PDDE"]:
    """The money an expense starts with for the secretaria: the PDDE only if it usually pays it."""
    return "PDDE" if rule == "SUGGESTED" else "APM"

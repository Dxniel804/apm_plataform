"""What each category is for the PDDE: the rules are code, so they are checked here."""

from app.expenses.category_rules import CATEGORY_RULES, rule_for
from app.seed_financial import DEFAULT_CATEGORIES


def test_every_expense_category_of_the_seed_has_a_rule() -> None:
    keys = {key for key, _name, applies_to, _group in DEFAULT_CATEGORIES if applies_to == "OUT"}
    assert keys <= set(CATEGORY_RULES), sorted(keys - set(CATEGORY_RULES))


def test_what_the_resolution_forbids_is_forbidden_for_the_pdde() -> None:
    # Res. CD/FNDE 15/2021, art. 4, par. 2: tarifa bancária and the tributos off the purchase.
    assert rule_for("bank_fees") == (None, "FORBIDDEN")
    assert rule_for("tax_payments") == (None, "FORBIDDEN")


def test_permanent_goods_are_capital_and_consumption_is_custeio() -> None:
    assert rule_for("capital_furniture") == ("CAPITAL", "SUGGESTED")
    assert rule_for("capital_equipment") == ("CAPITAL", "SUGGESTED")
    assert rule_for("cleaning_supplies") == ("CUSTEIO", "SUGGESTED")


def test_a_key_nobody_listed_is_left_to_the_person() -> None:
    assert rule_for("something_new") == (None, "ALLOWED")


def test_only_the_suggested_ones_carry_a_nature_the_site_can_trust() -> None:
    # A category with a nature is custeio or capital; the forbidden ones have none.
    for key, (nature, rule) in CATEGORY_RULES.items():
        assert nature in (None, "CUSTEIO", "CAPITAL"), key
        if rule == "FORBIDDEN":
            assert nature is None, key

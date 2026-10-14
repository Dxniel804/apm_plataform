"""The people of the expenses tests serve the settings too, and the committed school of the public
flow serves the contributions of the month."""

import pytest
from sqlalchemy import Engine, text

from tests.authsupport import UserFactory
from tests.expenses.conftest import scene, scene_with_limit  # noqa: F401
from tests.public.conftest import _clean_sandbox, other_school, school  # noqa: F401


@pytest.fixture(autouse=True)
def _default_settings(admin_engine: Engine, users: UserFactory) -> None:
    """The people of the scene live on schools that outlast a test: their settings start from the
    defaults every time."""
    world = users.world
    with admin_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE school_settings SET suggested_amounts_cents = '{2000,3000,4000}', "
                "allow_custom_amount = true, free_amount_text = NULL, monthly_goal_cents = NULL, "
                "expected_contributions = NULL WHERE school_id = ANY(:ids)"
            ),
            {"ids": [world.school_a1, world.school_a2, world.school_b1]},
        )

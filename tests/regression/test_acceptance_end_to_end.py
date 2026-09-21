import subprocess
import sys
from datetime import date
from decimal import Decimal

from construction_os.calc import calculate_portfolio, calculate_revenue_for_date
from construction_os.importers import parse_schedule, parse_vor, reconcile
from construction_os.money import round_position
from construction_os.references import RateType, get_rate


def test_acceptance_end_to_end(fixtures_dir, tmp_path):
    paths = [fixtures_dir / f"vor_object_{suffix}.xlsx" for suffix in ("a", "b", "c")]
    vors = [parse_vor(path) for path in paths]
    schedule = parse_schedule(fixtures_dir / "schedule_object_a.xlsx")
    rate = get_rate(RateType.VAT_RATE, date(2026, 9, 20)).value
    revenue_a = calculate_revenue_for_date(vors[0].total_gross, date(2026, 9, 20))
    portfolio = calculate_portfolio([vor.total_gross for vor in vors], date(2026, 9, 20))

    assert len(vors[0].items) == 29
    assert vors[0].total_gross == Decimal("35656922.00")
    assert rate == vors[0].vat_rate
    assert revenue_a.net == Decimal("29226985.25")
    assert revenue_a.vat == Decimal("6429936.75")
    assert schedule.total_amount == Decimal("35656922.00")
    assert reconcile(vors[0], schedule) == []
    assert portfolio.gross == Decimal("198690812.22")
    assert portfolio.net == Decimal("162861321.49")

    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    for output in (first_dir, second_dir):
        subprocess.run(
            [sys.executable, "scripts/make_fixtures.py", "--out", str(output)],
            check=True,
        )
    first = parse_vor(first_dir / "vor_object_a.xlsx")
    second = parse_vor(second_dir / "vor_object_a.xlsx")
    assert first.items == second.items
    assert first.total_gross == second.total_gross
    assert first.sha256 == second.sha256
    for vor in vors:
        assert all(
            item.amount_gross == round_position(item.quantity, item.price_gross)
            for item in vor.items
        )
    assert schedule.period_mismatches == ()
    assert vors[0].price_is_final is False

    subprocess.run(
        [
            sys.executable,
            "scripts/make_fixtures.py",
            "--out",
            str(tmp_path),
            "--shift-header",
            "2",
        ],
        check=True,
    )
    shifted = parse_vor(tmp_path / "vor_object_a_shifted_2.xlsx")
    assert len(shifted.items) == 29
    assert shifted.total_gross == Decimal("35656922.00")
    assert shifted.sha256 == vors[0].sha256

    quantity_by_position: dict[int, Decimal] = {}
    amount_by_position: dict[int, Decimal] = {}
    for task in schedule.tasks:
        assert task.position_no is not None
        quantity_by_position[task.position_no] = quantity_by_position.get(
            task.position_no, Decimal("0")
        ) + (task.quantity or Decimal("0"))
        amount_by_position[task.position_no] = amount_by_position.get(
            task.position_no, Decimal("0")
        ) + (task.amount or Decimal("0"))
    for item in vors[0].items:
        assert quantity_by_position[item.position_no] == item.quantity
        assert amount_by_position[item.position_no] == item.amount_gross

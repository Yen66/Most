from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from construction_os.importers import parse_vor
from construction_os.money import round_position


def test_vor_a_count(fixtures_dir):
    assert len(parse_vor(fixtures_dir / "vor_object_a.xlsx").items) == 29


def test_vor_a_total(fixtures_dir):
    assert parse_vor(fixtures_dir / "vor_object_a.xlsx").total_gross == Decimal("35656922.00")


def test_vor_a_header_found_by_content(fixtures_dir):
    assert parse_vor(fixtures_dir / "vor_object_a.xlsx").header_row == 9


def test_vor_a_formula_cache_absence_is_supported(fixtures_dir):
    parsed = parse_vor(fixtures_dir / "vor_object_a.xlsx")
    assert parsed.items[0].amount_formula == "=ROUND(D11*E11,2)"
    assert parsed.items[0].amount_gross == Decimal("85720.38")


def test_vor_a_formula_position_recovered(fixtures_dir):
    parsed = parse_vor(fixtures_dir / "vor_object_a.xlsx")
    assert [item.position_no for item in parsed.items] == list(range(1, 30))


def test_vor_a_price_not_final(fixtures_dir):
    assert parse_vor(fixtures_dir / "vor_object_a.xlsx").price_is_final is False


def test_vor_all_position_amount_invariant(fixtures_dir):
    for suffix in ("a", "b", "c"):
        parsed = parse_vor(fixtures_dir / f"vor_object_{suffix}.xlsx")
        assert all(item.amount_gross == round_position(item.quantity, item.price_gross) for item in parsed.items)


def test_vor_reparse_same_digest(fixtures_dir):
    path = fixtures_dir / "vor_object_a.xlsx"
    first = parse_vor(path)
    second = parse_vor(path)
    assert first == second
    assert first.sha256 == second.sha256

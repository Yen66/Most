from decimal import Decimal

from construction_os.importers import parse_schedule, parse_vor, reconcile


def test_schedule_total(fixtures_dir):
    parsed = parse_schedule(fixtures_dir / "schedule_object_a.xlsx")
    assert parsed.total_amount == Decimal("35656922.00")


def test_schedule_has_43_tasks(fixtures_dir):
    assert len(parse_schedule(fixtures_dir / "schedule_object_a.xlsx").tasks) == 43


def test_schedule_periods_sum_to_task_quantity(fixtures_dir):
    parsed = parse_schedule(fixtures_dir / "schedule_object_a.xlsx")
    assert parsed.period_mismatches == ()


def test_schedule_notes_are_parsed(fixtures_dir):
    parsed = parse_schedule(fixtures_dir / "schedule_object_a.xlsx")
    assert {note["type"] for note in parsed.notes} == {"period", "resource_plan", "reverse_scheme", "work_regime"}


def test_schedule_resource_sharing_uses_anonymized_names(fixtures_dir):
    parsed = parse_schedule(fixtures_dir / "schedule_object_a.xlsx")
    resource = next(note for note in parsed.notes if note["type"] == "resource_plan")["shared_resource"]
    assert resource["objects"] == ["Северная", "Восточная"]
    assert resource["crew"] == "10"


def test_schedule_reconciles_all_positions(fixtures_dir):
    vor = parse_vor(fixtures_dir / "vor_object_a.xlsx")
    schedule = parse_schedule(fixtures_dir / "schedule_object_a.xlsx")
    assert reconcile(vor, schedule) == []

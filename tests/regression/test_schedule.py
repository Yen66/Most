from datetime import date
from decimal import Decimal

from construction_os.importers import parse_schedule, parse_vor, reconcile


def test_schedule_total(fixtures_dir):
    parsed = parse_schedule(fixtures_dir / "schedule_object_a.xlsx")
    assert parsed.total_amount == Decimal("35656922.00")


def test_schedule_reconciles_all_positions(fixtures_dir):
    vor = parse_vor(fixtures_dir / "vor_object_a.xlsx")
    schedule = parse_schedule(fixtures_dir / "schedule_object_a.xlsx")
    assert reconcile(vor, schedule) == []
    assert {task.position_no for task in schedule.tasks if task.position_no is not None} == set(
        range(1, 30)
    )


def test_schedule_periods_sum_to_task_quantity(fixtures_dir):
    parsed = parse_schedule(fixtures_dir / "schedule_object_a.xlsx")
    assert parsed.period_mismatches == ()


def test_schedule_notes_are_parsed(fixtures_dir):
    parsed = parse_schedule(fixtures_dir / "schedule_object_a.xlsx")
    assert {note["type"] for note in parsed.notes} == {
        "period",
        "resource_plan",
        "reverse_scheme",
        "work_regime",
    }
    work_regime = next(note for note in parsed.notes if note["type"] == "work_regime")
    assert "плановое календарное распределение" in work_regime["text"].lower()
    assert "не подтверждённая норма выработки" in work_regime["text"].lower()


def test_schedule_resource_sharing_is_structured(fixtures_dir):
    parsed = parse_schedule(fixtures_dir / "schedule_object_a.xlsx")
    resource = next(note for note in parsed.notes if note["type"] == "resource_plan")[
        "shared_resource"
    ]
    assert resource == {
        "resource": "мобильная бригада",
        "objects": ["Северная", "Восточная"],
        "from": "2026-10-10",
        "crew": "10",
    }


def test_schedule_preserves_dates_duration_and_crew_as_data(fixtures_dir):
    parsed = parse_schedule(fixtures_dir / "schedule_object_a.xlsx")
    assert all(task.start_on is not None and task.end_on is not None for task in parsed.tasks)
    assert all(task.days is not None and task.crew_size is not None for task in parsed.tasks)
    first = next(task for task in parsed.tasks if task.position_no == 1)
    assert first.start_on == date(2026, 10, 5)
    assert first.end_on == date(2026, 10, 9)
    assert first.days == 5
    assert first.crew_size == Decimal("5")

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from construction_os.cli_contract import run_contract
from construction_os.references import DEFAULT_COST_ARTICLES
from construction_os.storage.contracts_service import get_contract, set_contract
from construction_os.storage.models import (
    CompanyRow,
    ContractRow,
    CostArticleRow,
    CostEntryRow,
    ObjectRow,
    ValueRefRow,
    ValueSourceRow,
    WorkItemRow,
)
from construction_os.storage.repositories import ContractRepository, ImmutableRecordError
from construction_os.storage.verdict import load_verdict

D = Decimal
DAY = date(2026, 9, 20)


def company(session, name="A"):
    row = CompanyRow(name=name)
    session.add(row)
    session.flush()
    return row


def demo(session):
    c = company(session, "Demo Co")
    for i, (code, category, name) in enumerate(DEFAULT_COST_ARTICLES, 1):
        session.add(CostArticleRow(code=code, category=category, name=name, sort_order=i))
    session.flush()
    source = ValueSourceRow(company_id=c.id, source_type="user_input", confidence="exact")
    session.add(source)
    session.flush()
    obj = ObjectRow(company_id=c.id, name="Demo Object", valid_from=DAY)
    session.add(obj)
    session.flush()
    session.add(
        WorkItemRow(
            company_id=c.id,
            object_id=obj.id,
            position_no=1,
            name="Demo",
            unit="шт",
            quantity=D("1"),
            price_gross=D("1220000"),
            amount_gross=D("1220000"),
            vat_rate=D("0.22"),
            source_id=source.id,
            valid_from=DAY,
        )
    )
    for code, amount in (
        ("MAT", "500000"),
        ("LAB", "250000"),
        ("MACH_OWN", "70000"),
        ("OVR_SITE", "50000"),
        ("BANK_GUAR", "27000"),
    ):
        session.add(
            CostEntryRow(
                company_id=c.id,
                object_id=obj.id,
                article_code=code,
                amount=D(amount),
                amount_type="fixed",
                vat_mode="net",
                source_id=source.id,
                created_by="test",
                valid_from=DAY,
            )
        )
    session.flush()
    return c, obj


def test_create_first_version(sqlite_session):
    company(sqlite_session)
    row, warnings = set_contract(
        sqlite_session, "A", "N-1", signed_on=DAY, contract_type="government", effective_on=DAY
    )
    _, current, count = get_contract(sqlite_session, "A", "N-1")
    assert row.id == current.id
    assert count == 1
    assert current.signed_on == DAY
    assert warnings == []


def test_supersede_preserves_history(sqlite_session):
    company(sqlite_session)
    old, _ = set_contract(sqlite_session, "A", "N", advance_pct=D("10"), effective_on=DAY)
    new, _ = set_contract(
        sqlite_session,
        "A",
        "N",
        advance_pct=D("20"),
        reason="уточнение аванса",
        actor="owner",
        effective_on=date(2026, 9, 21),
    )
    _, active, count = get_contract(sqlite_session, "A", "N")
    assert count == 2
    assert active.id == new.id
    assert old.valid_to == date(2026, 9, 21)
    assert old.superseded_by == new.id
    assert active.replace_reason == "уточнение аванса"
    assert active.advance_pct == D("20")


@pytest.mark.parametrize(
    ("terms", "message"),
    [
        ({"advance_pct": D("101")}, "advance_pct must be within 0..100"),
        ({"warranty_retention_pct": D("21")}, "warranty_retention_pct must be within 0..20"),
        ({"penalty_cap_pct": D("51")}, "penalty_cap_pct must be within 0..50"),
        ({"payment_delay_days": 31}, "payment_delay_days must be within 1..30"),
        ({"payment_delay_days": 0}, "payment_delay_days must be within 1..30"),
        ({"award_reduction_factor": D("0")}, "award_reduction_factor must be within (0, 1]"),
        ({"award_reduction_factor": D("1.1")}, "award_reduction_factor must be within (0, 1]"),
    ],
)
def test_e_v6_exact_validation(sqlite_session, terms, message):
    company(sqlite_session)
    with pytest.raises(ValueError, match=__import__("re").escape(message)):
        set_contract(sqlite_session, "A", "N", **terms)


def test_number_required(sqlite_session):
    company(sqlite_session)
    with pytest.raises(ValueError, match="contract number is required"):
        set_contract(sqlite_session, "A", "")


def test_payment_delay_warning(sqlite_session):
    company(sqlite_session)
    row, warnings = set_contract(sqlite_session, "A", "N", payment_delay_days=15)
    assert row.payment_delay_days == 15
    assert any("13.1" in warning for warning in warnings)


def test_provenance_exact_user_input(sqlite_session):
    c = company(sqlite_session)
    row, _ = set_contract(
        sqlite_session, "A", "N", award_reduction_factor=D("0.87"), actor="owner"
    )
    refs = list(
        sqlite_session.scalars(
            select(ValueRefRow).where(
                ValueRefRow.company_id == c.id,
                ValueRefRow.entity_name == "contracts",
                ValueRefRow.entity_id == row.id,
            )
        )
    )
    assert {"number", "award_reduction_factor"} <= {ref.field_name for ref in refs}
    sources = [sqlite_session.get(ValueSourceRow, ref.source_id) for ref in refs]
    assert all(source.source_type == "user_input" for source in sources)
    assert all(source.confidence == "exact" for source in sources)
    assert all("owner" in source.note for source in sources)


def test_tenant_isolation(sqlite_session):
    company(sqlite_session, "A")
    company(sqlite_session, "B")
    a, _ = set_contract(sqlite_session, "A", "N", advance_pct=D("10"))
    b, _ = set_contract(sqlite_session, "B", "N", advance_pct=D("20"))
    assert a.company_id != b.company_id
    assert get_contract(sqlite_session, "A", "N")[1].advance_pct == D("10")
    assert get_contract(sqlite_session, "B", "N")[1].advance_pct == D("20")


def test_unknown_company_not_created(sqlite_session):
    with pytest.raises(LookupError, match="нет данных: компания"):
        set_contract(sqlite_session, "Absent", "N")
    assert sqlite_session.scalar(select(func.count()).select_from(CompanyRow)) == 0


def test_immutable_repository(sqlite_session):
    company(sqlite_session)
    set_contract(sqlite_session, "A", "N")
    with pytest.raises(ImmutableRecordError):
        ContractRepository(sqlite_session).update(number="changed")


def test_cli_set_show_roundtrip(sqlite_session, capsys):
    company(sqlite_session)
    data = dict(
        company="A",
        number="N",
        signed_on=DAY,
        contract_type="government",
        advance_pct=D("20"),
        payment_delay_days=15,
        security_amount=D("1000"),
        warranty_retention_pct=D("5"),
        treasury_account=True,
        award_reduction_factor=D("0.87"),
        price_is_final=True,
        penalty_cap_pct=D("10"),
        actor="owner",
        reason="first",
    )
    assert run_contract(SimpleNamespace(contract_command="set", **data), sqlite_session) == 0
    out = capsys.readouterr().out
    assert "ПРЕДУПРЕЖДЕНИЕ" in out
    assert run_contract(SimpleNamespace(contract_command="show", company="A", number="N"), sqlite_session) == 0
    shown = capsys.readouterr().out
    assert "версий в истории: 1" in shown
    assert "award_reduction_factor: 0.870000" in shown
    assert "treasury_account: True" in shown


def test_factor_087_demo_verdict_e_v5(sqlite_session):
    c, obj = demo(sqlite_session)
    contract, _ = set_contract(
        sqlite_session,
        "Demo Co",
        "ДЕМО-АКТ-2026",
        award_reduction_factor=D("0.87"),
        effective_on=date(2026, 9, 21),
    )
    current_obj = sqlite_session.scalar(
        select(ObjectRow).where(ObjectRow.company_id == c.id, ObjectRow.valid_to.is_(None))
    )
    assert current_obj.id != obj.id
    assert current_obj.contract_id == contract.id
    verdict = load_verdict(sqlite_session, "Demo Co", "Demo Object", DAY)
    assert verdict.bids[-1].net == D("870000.00")
    assert verdict.report.profit.profit_before_tax == D("103000.00")
    assert verdict.status == "ВХОДИТЬ"


def test_replacing_contract_updates_object_link(sqlite_session):
    c, _ = demo(sqlite_session)
    first, _ = set_contract(sqlite_session, "Demo Co", "N", effective_on=DAY)
    second, _ = set_contract(
        sqlite_session, "Demo Co", "N", advance_pct=D("10"), effective_on=date(2026, 9, 21)
    )
    current = sqlite_session.scalar(
        select(ObjectRow).where(ObjectRow.company_id == c.id, ObjectRow.valid_to.is_(None))
    )
    assert first.id != second.id
    assert current.contract_id == second.id


def test_contract_not_found_show(sqlite_session, capsys):
    company(sqlite_session)
    assert run_contract(
        SimpleNamespace(contract_command="show", company="A", number="missing"), sqlite_session
    ) == 2
    assert "нет данных: договор missing" in capsys.readouterr().out

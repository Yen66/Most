from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from construction_os.calc.verdict import (
    BID_REDUCTIONS,
    RISK_CODES,
    bid_grid,
    cost_completeness,
    traffic_light,
    vat_warnings,
)
from construction_os.cli_verdict import run_verdict
from construction_os.importers.persist import persist_vor
from construction_os.importers.vor import parse_vor
from construction_os.references import DEFAULT_COST_ARTICLES
from construction_os.storage.models import (
    Base,
    CompanyRow,
    ContractRow,
    CostArticleRow,
    CostEntryRow,
    ObjectRow,
    ValueSourceRow,
    WorkItemRow,
)
from construction_os.storage.verdict import load_verdict

D = Decimal
DAY = date(2026, 9, 20)
EXPECTED = (
    ("0", "35656922.00", "29226985.25", "6429936.75", "0.00"),
    ("0.05", "33874075.93", "27765636.01", "6108439.92", "-1461349.24"),
    ("0.08", "32804368.25", "26888826.43", "5915541.82", "-2338158.82"),
    ("0.10", "32091229.83", "26304286.75", "5786943.08", "-2922698.50"),
    ("0.15", "30308383.71", "24842937.47", "5465446.24", "-4384047.78"),
    ("0.20", "28525537.58", "23381588.18", "5143949.40", "-5845397.07"),
    ("0.22", "27812399.16", "22797048.49", "5015350.67", "-6429936.76"),
)


def catalog(session):
    for n, (code, category, name) in enumerate(DEFAULT_COST_ARTICLES, 1):
        session.add(CostArticleRow(code=code, category=category, name=name, sort_order=n))
    session.flush()


def vor_a(session, fixtures_dir, company="A"):
    path = fixtures_dir / "vor_object_a.xlsx"
    persist_vor(session, company, parse_vor(path), path, imported_on=DAY)
    session.flush()


def demo(session, factor=None, vat=D("0.22")):
    catalog(session)
    company = CompanyRow(name="Demo Co")
    session.add(company)
    session.flush()
    source = ValueSourceRow(company_id=company.id, source_type="user_input", confidence="exact")
    session.add(source)
    session.flush()
    contract = None
    if factor is not None:
        contract = ContractRow(
            company_id=company.id,
            contract_type="government",
            number="ДЕМО-АКТ-2026",
            award_reduction_factor=factor,
            valid_from=DAY,
        )
        session.add(contract)
        session.flush()
    obj = ObjectRow(
        company_id=company.id,
        name="Demo Object",
        contract_id=contract.id if contract else None,
        valid_from=DAY,
    )
    session.add(obj)
    session.flush()
    session.add(
        WorkItemRow(
            company_id=company.id,
            object_id=obj.id,
            contract_id=obj.contract_id,
            position_no=1,
            name="Demo",
            unit="шт",
            quantity=D("1"),
            price_gross=D("1220000"),
            amount_gross=D("1220000"),
            vat_rate=vat,
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
                company_id=company.id,
                object_id=obj.id,
                contract_id=obj.contract_id,
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
    return company, obj


def args(company, object_name):
    return SimpleNamespace(company=company, object=object_name, date=DAY)


def test_e_v1_all_rows_from_real_fixture(fixtures_dir):
    parsed = parse_vor(fixtures_dir / "vor_object_a.xlsx")
    rows = bid_grid([item.amount_gross for item in parsed.items], D("0.22"))
    assert len(parsed.items) == 29
    assert len(rows) == len(EXPECTED)
    for row, expected in zip(rows, EXPECTED, strict=True):
        assert (row.reduction, row.gross, row.net, row.vat, row.delta_net) == tuple(
            map(D, expected)
        )


def test_bid_grid_zero_matches_historical_revenue(fixtures_dir):
    parsed = parse_vor(fixtures_dir / "vor_object_a.xlsx")
    row = bid_grid([item.amount_gross for item in parsed.items], D("0.22"))[0]
    assert row.net == D("29226985.25")
    assert row.vat == D("6429936.75")


def test_bid_grid_monotonic(fixtures_dir):
    parsed = parse_vor(fixtures_dir / "vor_object_a.xlsx")
    rows = bid_grid([item.amount_gross for item in parsed.items], D("0.22"))
    assert all(a.net > b.net for a, b in zip(rows, rows[1:]))


def test_bid_grid_fixed_reductions():
    assert BID_REDUCTIONS == tuple(map(D, ("0", "0.05", "0.08", "0.10", "0.15", "0.20", "0.22")))


def test_bid_grid_award_factor_e_v5():
    rows = bid_grid([D("1220000")], D("0.22"), D("0.87"))
    award = rows[-1]
    assert award.is_award
    assert (award.reduction, award.gross, award.net) == (
        D("0.13"),
        D("1061400.00"),
        D("870000.00"),
    )


def test_invalid_award_factor():
    for factor in (D("0"), D("-0.1"), D("1.01")):
        with pytest.raises(ValueError, match="award_reduction_factor"):
            bid_grid([D("100")], D("0.22"), factor)


def test_completeness_missing_6_and_23():
    result = cost_completeness(set(), [code for code, _, _ in DEFAULT_COST_ARTICLES])
    assert result.risks == RISK_CODES
    assert len(result.missing_other) == 23
    assert result.present_count == 0


def test_completeness_demo_6_and_18():
    present = {"MAT", "LAB", "MACH_OWN", "OVR_SITE", "BANK_GUAR"}
    result = cost_completeness(present, [code for code, _, _ in DEFAULT_COST_ARTICLES])
    assert result.risks == RISK_CODES
    assert len(result.missing_other) == 18
    assert result.present_count == 5


@pytest.mark.parametrize(
    ("profit", "expected"),
    [
        ("103000", "ВХОДИТЬ"),
        ("100000", "ВХОДИТЬ"),
        ("30000", "ОСТОРОЖНО — запас тонкий"),
        ("29999", "НЕ ВХОДИТЬ"),
        ("0", "НЕ ВХОДИТЬ"),
        ("-27000", "НЕ ВХОДИТЬ"),
    ],
)
def test_traffic_light_thresholds(profit, expected):
    assert traffic_light(D(profit), D("1000000")) == expected


def test_traffic_light_missing_costs():
    assert traffic_light(None, D("1000000")) is None


def test_vat_warning_20_vs_22():
    warnings = vat_warnings({D("0.20")}, D("0.22"), DAY)
    assert len(warnings) == 1
    assert "20%" in warnings[0]
    assert "22%" in warnings[0]


def test_vat_warning_matching_rate():
    assert vat_warnings({D("0.22")}, D("0.22"), DAY) == ()


def test_cli_vor_no_costs(sqlite_session, fixtures_dir, capsys):
    catalog(sqlite_session)
    vor_a(sqlite_session, fixtures_dir)
    assert run_verdict(args("A", "vor_object_a"), sqlite_session) == 0
    out = capsys.readouterr().out
    assert "29 226 985,25" in out
    assert "26 304 286,75" in out
    assert "вердикт неполный" in out
    assert "светофор:" not in out


def test_db_bid_grid_exact_e_v1(sqlite_session, fixtures_dir):
    catalog(sqlite_session)
    vor_a(sqlite_session, fixtures_dir)
    report = load_verdict(sqlite_session, "A", "vor_object_a", DAY)
    assert report.positions == 29
    assert report.bids[0].net == D("29226985.25")
    assert report.bids[3].net == D("26304286.75")
    assert len(report.completeness.risks) == 6
    assert len(report.completeness.missing_other) == 23


def test_demo_base_margin_e_v3(sqlite_session):
    demo(sqlite_session)
    verdict = load_verdict(sqlite_session, "Demo Co", "Demo Object", DAY)
    assert verdict.report.profit.profit_before_tax == D("103000.00")
    assert verdict.report.profit.margin_pct == D("10.30")
    assert verdict.status == "ВХОДИТЬ"
    assert len(verdict.completeness.missing_other) == 18


def test_demo_factor_e_v5(sqlite_session, capsys):
    demo(sqlite_session, D("0.87"))
    assert run_verdict(args("Demo Co", "Demo Object"), sqlite_session) == 0
    out = capsys.readouterr().out
    assert "ваше снижение 13,00" in out
    assert "870 000,00" in out
    assert "−27 000,00" in out or "-27 000,00" in out
    assert "НЕ ВХОДИТЬ" in out


def test_unknown_object_exit_two(sqlite_session, capsys):
    assert run_verdict(args("A", "missing"), sqlite_session) == 2
    assert "нет данных: объект missing компании A" in capsys.readouterr().out


def test_verdict_tenant_isolation(sqlite_session, fixtures_dir):
    catalog(sqlite_session)
    vor_a(sqlite_session, fixtures_dir, "A")
    with pytest.raises(LookupError, match="нет данных"):
        load_verdict(sqlite_session, "B", "vor_object_a", DAY)


def test_verdict_read_only(sqlite_session, fixtures_dir):
    catalog(sqlite_session)
    vor_a(sqlite_session, fixtures_dir)
    before = {
        table.name: sqlite_session.scalar(select(func.count()).select_from(table))
        for table in Base.metadata.sorted_tables
    }
    load_verdict(sqlite_session, "A", "vor_object_a", DAY)
    after = {
        table.name: sqlite_session.scalar(select(func.count()).select_from(table))
        for table in Base.metadata.sorted_tables
    }
    assert after == before

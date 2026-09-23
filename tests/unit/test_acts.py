from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from construction_os.calc.acts import (
    LONG_CONTRACT_WARNING,
    UNKNOWN_EIS_WARNING,
    payment_deadline,
    payment_term,
    signing_deadline,
)
from construction_os.references.calendar_seed import iter_calendar_days
from construction_os.storage.acts import (
    ActFlowError,
    change_act_status,
    create_act,
    current_obligation,
    register_payment,
    validate_act,
    validate_payment,
)
from construction_os.storage.calendar import DbCalendar
from construction_os.storage.models import (
    AcceptanceActRow,
    CompanyRow,
    PaymentObligationRow,
    WorkCalendarRow,
)
from construction_os.storage.repositories import (
    AcceptanceActRepository,
    ContractRepository,
    DuplicateActiveVersionError,
    ImmutableRecordError,
    PaymentObligationRepository,
)

D = date.fromisoformat
M = Decimal


@pytest.fixture
def context(sqlite_session):
    for year in (2026, 2027):
        sqlite_session.add_all(WorkCalendarRow(**r) for r in iter_calendar_days(year))
    company = CompanyRow(name="Acts Co")
    other = CompanyRow(name="Other Co")
    sqlite_session.add_all([company, other])
    sqlite_session.flush()
    contract = ContractRepository(sqlite_session).add(
        company.id, contract_type="government", number="44-FZ",
        signed_on=D("2026-08-01"), price_is_final=True,
        valid_from=D("2026-08-01"),
    )
    return sqlite_session, company, other, contract


@pytest.mark.parametrize(
    "status,placed,signed,refusal,reason,expected",
    [
        ("placed", None, None, None, None, "act status placed requires placed_on"),
        ("signed", D("2026-09-01"), None, None, None,
         "act status signed requires signed_on"),
        ("refused", D("2026-09-01"), None, D("2026-09-20"), None,
         "act status refused requires refusal_reason"),
        ("signed", D("2026-09-01"), D("2026-09-29"), D("2026-09-20"), "x",
         "act cannot be both signed and refused"),
    ],
)
def test_act_flow_error_texts(status, placed, signed, refusal, reason, expected):
    with pytest.raises(ActFlowError) as error:
        validate_act(status, placed, signed, refusal, reason)
    assert str(error.value) == expected


@pytest.mark.parametrize(
    "paid_on,paid_amount,expected",
    [
        (None, M("1"), "paid_amount requires paid_on"),
        (D("2026-10-08"), None, "paid_on requires paid_amount"),
        (D("2026-10-08"), M("101"), "paid_amount cannot exceed obligation amount"),
    ],
)
def test_payment_error_texts(paid_on, paid_amount, expected):
    with pytest.raises(ActFlowError) as error:
        validate_payment(M("100"), paid_on, paid_amount)
    assert str(error.value) == expected


@pytest.mark.parametrize(
    "treasury,eis,override,days,basis",
    [
        (False, True, None, 7, "law_eis_7"),
        (True, True, None, 10, "law_treasury_10"),
        (False, False, None, 10, "law_non_eis_10"),
        (False, True, 9, 9, "contract"),
        (False, None, None, 7, "law_eis_7"),
    ],
)
def test_payment_term_branches(treasury, eis, override, days, basis):
    warnings = []
    contract = SimpleNamespace(
        treasury_account=treasury, payment_delay_days=override
    )
    assert payment_term(contract, eis, warnings) == (days, basis)
    if eis is None:
        assert UNKNOWN_EIS_WARNING in warnings


def test_long_contract_warning():
    warnings = []
    assert payment_term(
        SimpleNamespace(treasury_account=False, payment_delay_days=12),
        True, warnings,
    ) == (12, "contract")
    assert warnings == [LONG_CONTRACT_WARNING]


def test_signed_act_creates_obligation(context):
    session, company, _, contract = context
    act, obligation, warnings = create_act(
        session, company.id, contract, "A1", M("1000000"),
        D("2026-09-01"), signed_on=D("2026-09-29"), via_eis=True,
    )
    assert act.status == "signed" and warnings == []
    assert obligation.amount == M("1000000.00")
    assert obligation.due_on == D("2026-10-08")
    assert obligation.term_basis == "law_eis_7"
    assert current_obligation(session, company.id, act.id).id == obligation.id


def test_refused_act_has_no_payment(context):
    session, company, _, contract = context
    act, obligation, _ = create_act(
        session, company.id, contract, "A1", M("100"),
        D("2026-09-01"), refusal_on=D("2026-09-20"),
        refusal_reason="Замечания",
    )
    assert act.status == "refused" and obligation is None
    assert current_obligation(session, company.id, act.id) is None


def test_duplicate_placed_or_signed_rejected(context):
    session, company, _, contract = context
    for number, signed in (("placed", None), ("signed", D("2026-09-29"))):
        create_act(
            session, company.id, contract, number, M("100"),
            D("2026-09-01"), signed_on=signed,
        )
        with pytest.raises(DuplicateActiveVersionError):
            create_act(
                session, company.id, contract, number, M("100"),
                D("2026-09-25"),
            )


def test_refusal_replacement_resets_deadline(context):
    session, company, _, contract = context
    first, _, _ = create_act(
        session, company.id, contract, "A1", M("100"),
        D("2026-09-01"), refusal_on=D("2026-09-20"),
        refusal_reason="Замечания",
    )
    new, _, _ = create_act(
        session, company.id, contract, "A1", M("100"), D("2026-09-25"),
    )
    assert new.id != first.id and first.superseded_by == new.id
    assert new.replace_reason == "повторное размещение после мотивированного отказа"
    assert signing_deadline(
        new.placed_on, DbCalendar(session).is_working
    ) == D("2026-10-23")


def test_placed_to_signed_historical_status(context):
    session, company, _, contract = context
    first, _, _ = create_act(
        session, company.id, contract, "A1", M("1000000"), D("2026-09-01"),
    )
    signed, obligation, _ = change_act_status(
        session, company.id, first, signed_on=D("2026-09-29"),
    )
    repo = AcceptanceActRepository(session)
    assert repo.get_on_date(company.id, first.id, D("2026-09-15")).status == "placed"
    assert first.valid_to == D("2026-09-29")
    assert signed.status == "signed" and obligation.due_on == D("2026-10-08")
    assert [a.id for a in repo.list_current(company.id)] == [signed.id]


def test_partial_payment_supersedes_and_rejects_second(context):
    session, company, _, contract = context
    act, obligation, _ = create_act(
        session, company.id, contract, "A1", M("1000000"),
        D("2026-09-01"), signed_on=D("2026-09-29"),
    )
    paid = register_payment(
        session, company.id, obligation, D("2026-10-10"), M("400000"),
    )
    assert paid.id != obligation.id
    assert obligation.superseded_by == paid.id
    assert paid.paid_amount == M("400000.00")
    assert current_obligation(session, company.id, act.id).id == paid.id
    with pytest.raises(ActFlowError, match="оплата уже зарегистрирована"):
        register_payment(session, company.id, paid, D("2026-10-11"), M("100"))


def test_tenant_isolation_new_repositories(context):
    session, company, other, contract = context
    act, obligation, _ = create_act(
        session, company.id, contract, "A1", M("100"),
        D("2026-09-01"), signed_on=D("2026-09-29"),
    )
    for repository, row in (
        (AcceptanceActRepository(session), act),
        (PaymentObligationRepository(session), obligation),
    ):
        assert repository.get(other.id, row.id) is None
        assert repository.list_current(other.id) == []
        with pytest.raises(ImmutableRecordError):
            repository.update(row.id)
        with pytest.raises(ImmutableRecordError):
            repository.delete(row.id)


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("placed", "ck_acts_status_requires_placed_on"),
        ("signed", "ck_acts_status_requires_signed_on"),
        ("refused", "ck_acts_status_requires_refusal"),
        ("both", "ck_acts_not_signed_and_refused"),
        ("amount", "ck_acts_amount_positive"),
    ],
)
def test_named_act_checks_raw(context, kind, expected):
    session, company, _, contract = context
    values = dict(
        company_id=company.id, contract_id=contract.id, act_number="RAW",
        amount_gross=M("100"), placed_on=D("2026-09-01"),
        status="placed", valid_from=D("2026-09-01"),
    )
    if kind == "placed":
        values["placed_on"] = None
    elif kind == "signed":
        values["status"] = "signed"
    elif kind == "refused":
        values["status"] = "refused"
        values["refusal_on"] = D("2026-09-20")
    elif kind == "both":
        values["signed_on"] = D("2026-09-29")
        values["refusal_on"] = D("2026-09-20")
    else:
        values["amount_gross"] = M("0")
    session.add(AcceptanceActRow(**values))
    with pytest.raises(IntegrityError, match=expected):
        session.flush()


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("pair", "ck_pay_obl_paid_pair"),
        ("range", "ck_pay_obl_paid_range"),
        ("amount", "ck_pay_obl_amount_positive"),
    ],
)
def test_named_payment_checks_raw(context, kind, expected):
    session, company, _, contract = context
    act, _, _ = create_act(
        session, company.id, contract, "A1", M("100"), D("2026-09-01"),
    )
    values = dict(
        company_id=company.id, act_id=act.id, amount=M("100"),
        due_on=D("2026-10-08"), term_workdays=7, term_basis="law_eis_7",
        valid_from=D("2026-09-29"),
    )
    if kind == "pair":
        values["paid_amount"] = M("10")
    elif kind == "range":
        values["paid_on"] = D("2026-10-08")
        values["paid_amount"] = M("101")
    else:
        values["amount"] = M("0")
    session.add(PaymentObligationRow(**values))
    with pytest.raises(IntegrityError, match=expected):
        session.flush()


def test_payment_deadline_matches_calendar(context):
    session, _, _, _ = context
    cal = DbCalendar(session).is_working
    assert payment_deadline(D("2026-09-29"), 7, cal) == D("2026-10-08")
    assert payment_deadline(D("2026-09-29"), 10, cal) == D("2026-10-13")


def test_act_provenance(context):
    session, company, _, contract = context
    act, obligation, _ = create_act(
        session, company.id, contract, "A1", M("100"),
        D("2026-09-01"), signed_on=D("2026-09-29"),
    )
    from construction_os.storage.models import ValueRefRow

    refs = session.scalars(
        select(ValueRefRow).where(ValueRefRow.company_id == company.id)
    ).all()
    assert any(r.entity_id == act.id and r.field_name == "amount_gross" for r in refs)
    assert any(r.entity_id == obligation.id and r.field_name == "due_on" for r in refs)

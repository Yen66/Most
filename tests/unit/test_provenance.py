from uuid import uuid4

from construction_os.provenance import ValueConfirmation, ValueRef, ValueSource
from construction_os.references import Confidence, SourceType


def test_source_has_company():
    company = uuid4()
    assert ValueSource(company, SourceType.DOCUMENT).company_id == company


def test_source_defaults_exact():
    assert ValueSource(uuid4(), SourceType.DOCUMENT).confidence == Confidence.EXACT


def test_source_cell_location():
    source = ValueSource(uuid4(), SourceType.DOCUMENT, sheet="Лист1", cell_or_range="D11", row_no=11)
    assert (source.sheet, source.cell_or_range, source.row_no) == ("Лист1", "D11", 11)


def test_value_ref_links_source():
    source_id = uuid4()
    ref = ValueRef(uuid4(), "work_items", uuid4(), "quantity", source_id)
    assert ref.source_id == source_id


def test_confirmation_records_actor():
    confirmation = ValueConfirmation(uuid4(), "work_items", uuid4(), "imported", "importer")
    assert confirmation.actor == "importer"


def test_provenance_ids_are_unique():
    left = ValueSource(uuid4(), SourceType.DOCUMENT)
    right = ValueSource(uuid4(), SourceType.DOCUMENT)
    assert left.id != right.id

from decimal import Decimal
from construction_os.money import extract_vat, from_excel_float, round_position, sum_positions

def test_excel_float_artifacts():
    assert from_excel_float(42860.189999999995) == Decimal("42860.19")
    assert from_excel_float(115397900.00000001) == Decimal("115397900.00")

def test_position_rounding():
    assert round_position(2, 42860.189999999995) == Decimal("85720.38")

def test_sum_already_rounded_positions():
    assert sum_positions([Decimal("1.005"), Decimal("1.005")]) == Decimal("2.02")

def test_reference_vat():
    pair = extract_vat(Decimal("35656922.00"), Decimal("0.22"))
    assert pair.net == Decimal("29226985.25")
    assert pair.vat == Decimal("6429936.75")
    assert pair.net + pair.vat == pair.gross

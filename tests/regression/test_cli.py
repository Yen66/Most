from construction_os.cli import main

def test_report(capsys):
    code=main(["report","--date","2026-09-20","--gross","35656922.00","115397900.00","47635990.22"])
    out=capsys.readouterr().out
    assert code==0 and "198 690 812.22 ₽" in out and "162 861 321.49 ₽" in out

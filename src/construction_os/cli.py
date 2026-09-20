from __future__ import annotations
import argparse
from datetime import date
from decimal import Decimal
from construction_os.calc import calculate_portfolio
from construction_os.importers import parse_schedule,parse_vor,reconcile
from construction_os.reports import format_money

def main(argv=None):
    p=argparse.ArgumentParser(prog="construction-os");sub=p.add_subparsers(dest="cmd",required=True)
    i=sub.add_parser("import");i.add_argument("path");i.add_argument("--kind",choices=["vor","schedule"],required=True)
    v=sub.add_parser("verify");v.add_argument("--vor",required=True);v.add_argument("--schedule",required=True)
    r=sub.add_parser("report");r.add_argument("--date",type=date.fromisoformat,required=True);r.add_argument("--gross",type=Decimal,nargs="+",required=True)
    a=p.parse_args(argv)
    if a.cmd=="import":
        x=parse_vor(a.path) if a.kind=="vor" else parse_schedule(a.path)
        print(x);return 0
    if a.cmd=="verify":
        x=parse_vor(a.vor);s=parse_schedule(a.schedule);d=reconcile(x,s)
        print(f"VOR total: {x.total_gross}");print(f"Schedule total: {s.total_amount}");print(f"Differences: {len(d)}")
        return 0 if not d and not s.period_mismatches else 1
    result=calculate_portfolio(a.gross,a.date)
    print(f"С НДС: {format_money(result.gross)}");print(f"Без НДС: {format_money(result.net)}");print(f"НДС: {format_money(result.vat)}")
    return 0
if __name__=="__main__":raise SystemExit(main())

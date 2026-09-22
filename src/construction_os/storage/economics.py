from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from sqlalchemy import func, select
from construction_os.calc import CostArticle,CostEntry,CostSummary,ProfitResult,ThresholdResult,breakeven_net,calculate_profit,calculate_revenue_for_date,max_price_reduction,summarize_costs
from construction_os.money import money
from construction_os.references import RateType,get_rate
from .models import CompanyRow,ContractRow,CostArticleRow,CostEntryRow,ObjectRow,WorkItemRow
from .queries import object_lineage_ids

@dataclass(frozen=True,slots=True)
class EconomicsReport:
    company:CompanyRow; object_row:ObjectRow; contract:ContractRow|None
    revenue_gross:Decimal; revenue_net:Decimal; vat:Decimal; vat_rate:Decimal
    costs:CostSummary|None; profit:ProfitResult|None; breakeven:ThresholdResult; max_reduction:ThresholdResult

def find_active_object(session,company_name:str,object_name:str)->tuple[CompanyRow,ObjectRow]:
    rows=session.execute(select(CompanyRow,ObjectRow).join(ObjectRow,ObjectRow.company_id==CompanyRow.id).where(CompanyRow.name==company_name,ObjectRow.name==object_name,ObjectRow.valid_to.is_(None))).all()
    if len(rows)!=1: raise LookupError(f"ожидалась одна активная версия объекта {object_name!r}, найдено: {len(rows)}")
    return rows[0]

def load_economics_report(session,company_name:str,object_name:str,on_date:date)->EconomicsReport:
    company,obj=find_active_object(session,company_name,object_name); lineage=object_lineage_ids(session,obj)
    gross=session.scalar(select(func.sum(WorkItemRow.amount_gross)).where(WorkItemRow.company_id==company.id,WorkItemRow.object_id.in_(lineage),WorkItemRow.valid_to.is_(None)))
    if gross is None: raise LookupError("у объекта нет актуальной выручки")
    revenue=calculate_revenue_for_date(money(gross),on_date)
    article_rows=list(session.scalars(select(CostArticleRow).where(CostArticleRow.is_active.is_(True))))
    articles={r.code:CostArticle(r.code,r.category,r.name,r.sort_order) for r in article_rows}
    cost_rows=list(session.scalars(select(CostEntryRow).where(CostEntryRow.company_id==company.id,CostEntryRow.object_id.in_(lineage),CostEntryRow.valid_to.is_(None))))
    entries=[CostEntry(r.article_code,r.amount,r.amount_type,r.rate_value,r.vat_mode,r.vat_rate,r.work_item_id) for r in cost_rows]
    costs=summarize_costs(entries,articles,set(articles),default_vat_rate=revenue.vat_rate)
    profit=None; be=ThresholdResult(None,"нет данных"); reduction=ThresholdResult(None,"нет данных")
    if costs is not None:
        tax=get_rate(RateType.PROFIT_TAX,on_date).value; profit=calculate_profit(revenue.net,costs.production,costs.financial_fixed,costs.financial_share,tax)
        be=breakeven_net(costs.production,costs.financial_fixed,costs.financial_share); reduction=max_price_reduction(revenue.net,be.value)
    contract=session.get(ContractRow,obj.contract_id) if obj.contract_id else None
    return EconomicsReport(company,obj,contract,revenue.gross,revenue.net,revenue.vat,revenue.vat_rate,costs,profit,be,reduction)

from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID
from construction_os.money import extract_vat, money


@dataclass(frozen=True, slots=True)
class CostArticle:
    code: str
    category: str
    name: str
    sort_order: int | None = None


@dataclass(frozen=True, slots=True)
class CostEntry:
    article_code: str
    amount: Decimal | None
    amount_type: str = "fixed"
    rate_value: Decimal | None = None
    vat_mode: str = "unknown"
    vat_rate: Decimal | None = None
    work_item_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CostSummary:
    by_article: dict[str, Decimal]
    by_category: dict[str, Decimal]
    production: Decimal
    financial_fixed: Decimal
    financial_share: Decimal
    unknown_vat_count: int
    unknown_vat_amount: Decimal
    warnings: tuple[str, ...]
    missing_articles: tuple[str, ...]
    complete: bool


def _net_amount(entry: CostEntry, default_vat_rate: Decimal | None) -> tuple[Decimal, bool]:
    if entry.amount is None:
        return Decimal("0"), False
    if entry.vat_mode == "gross":
        rate = entry.vat_rate or default_vat_rate
        if rate is not None:
            return extract_vat(entry.amount, rate).net, False
    if entry.vat_mode == "unknown":
        return money(entry.amount), True
    return money(entry.amount), False


def summarize_costs(
    entries: list[CostEntry],
    articles: dict[str, CostArticle],
    expected_article_codes: set[str] | None = None,
    default_vat_rate: Decimal | None = None,
) -> CostSummary | None:
    if not entries:
        return None
    by_article = {}
    by_category = {}
    financial_fixed = Decimal("0")
    financial_share = Decimal("0")
    unknown_count = 0
    unknown_amount = Decimal("0")
    warnings = []
    present = set()
    for entry in entries:
        article = articles[entry.article_code]
        present.add(article.code)
        if entry.amount_type == "share_of_revenue":
            financial_share += entry.rate_value or Decimal("0")
            continue
        amount, unknown = _net_amount(entry, default_vat_rate)
        if unknown:
            unknown_count += 1
            unknown_amount += amount
        by_article[article.code] = by_article.get(article.code, Decimal("0")) + amount
        by_category[article.category] = by_category.get(article.category, Decimal("0")) + amount
        if article.category == "financial":
            financial_fixed += amount
        if article.category == "other":
            warnings.append(f"{article.code}: статья не классифицирована, уточните категорию")
    production = sum((v for k, v in by_category.items() if k != "financial"), Decimal("0"))
    if unknown_count:
        warnings.append(
            f"{unknown_count} записей на сумму {money(unknown_amount)} ₽ имеют неопределённый режим НДС. Результат может быть занижен или завышен"
        )
    missing = tuple(sorted((expected_article_codes or set()) - present))
    return CostSummary(
        {k: money(v) for k, v in by_article.items()},
        {k: money(v) for k, v in by_category.items()},
        money(production),
        money(financial_fixed),
        financial_share,
        unknown_count,
        money(unknown_amount),
        tuple(warnings),
        missing,
        not missing and unknown_count == 0,
    )

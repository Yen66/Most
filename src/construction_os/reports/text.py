from decimal import Decimal

def format_money(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", " ") + " ₽"

def format_percent(value: Decimal) -> str:
    return f"{value:.2f} %".replace(".", ",")

def format_money_ru(value: Decimal) -> str:
    raw=f"{value:,.2f}"
    return raw.replace(","," ").replace(".",",")+" ₽"

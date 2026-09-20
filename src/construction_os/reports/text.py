from decimal import Decimal
def format_money(value:Decimal)->str:
    return f"{value:,.2f}".replace(","," ")+" ₽"

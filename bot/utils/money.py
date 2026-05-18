from decimal import Decimal


def fmt_amount(amount: Decimal | int | float, currency: str) -> str:
    if currency == "XTR":
        return f"{int(amount)} ⭐"
    if currency == "RUB":
        return f"{Decimal(amount).normalize():f} ₽"
    return f"{Decimal(amount).normalize():f} {currency}"

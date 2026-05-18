from decimal import Decimal


def fmt_amount(amount: Decimal | int | float, currency: str) -> str:
    if currency == "XTR":
        return f"{int(amount)} ⭐"
    if currency == "RUB":
        return f"{Decimal(amount).normalize():f} ₽"
    # USDT and USD are treated as the same currency in the UI.
    if currency in ("USDT", "USD"):
        return f"${Decimal(amount).normalize():f}"
    return f"{Decimal(amount).normalize():f} {currency}"

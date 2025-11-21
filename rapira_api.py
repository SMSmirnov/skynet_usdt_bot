import httpx
import time
from config import settings

RAPIRA_RATES_URL = settings.rapira_base_url.rstrip("/") + "/open/market/rates"

_cached_rates = None
_cache_timestamp = 0
_CACHE_TTL = 60  # кеш 60 секунд

CLIENT_MARGIN = 0.30  # наша наценка

async def fetch_usdt_rub_rate():
    """
    Возвращает скорректированные курсы:
      - Клиент продаёт USDT нам → мы ориентируемся на bidPrice (Rapira покупает) минус маржа
      - Клиент покупает USDT у нас → мы ориентируемся на askPrice (Rapira продаёт) плюс маржа
    Возвращает словарь: {'buy_to_client': <курс когда клиент покупает USDT>,
                         'sell_from_client': <курс когда клиент продаёт USDT>}  
    """
    global _cached_rates, _cache_timestamp

    now = time.time()
    if _cached_rates is not None and (now - _cache_timestamp) < _CACHE_TTL:
        return _cached_rates

    headers = {"accept": "application/json"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(RAPIRA_RATES_URL, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    for item in data.get("data", []):
        if item.get("symbol") == "USDT/RUB":
            bid = item.get("bidPrice")
            ask = item.get("askPrice")
            if bid is None or ask is None:
                return None

            # Логика:
            # клиент отдаёт USDT нам → мы платим рубли → мы используем bidPrice минус маржа
            sell_from_client = bid - CLIENT_MARGIN
            # клиент покупает USDT у нас → он платит рубли → мы используем askPrice плюс маржа
            buy_to_client = ask + CLIENT_MARGIN

            _cached_rates = {
                "buy_to_client": buy_to_client,
                "sell_from_client": sell_from_client
            }
            _cache_timestamp = now
            return _cached_rates

    return None


# ========== Тестовый запуск функции ==========
if __name__ == "__main__":
    import asyncio
    async def test():
        rates = await fetch_usdt_rub_rate()
        print("Rates:", rates)
    asyncio.run(test())

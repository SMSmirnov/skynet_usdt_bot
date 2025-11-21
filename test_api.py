import httpx
from config import settings

async def test_rates():
    url = settings.rapira_base_url + "/open/market/rates"
    headers = {
        "accept": "application/json",
        # если нужен авторизационный ключ:
        # "Authorization": f"Bearer {settings.rapira_api_key}"
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, headers=headers)
        print("Status:", resp.status_code)
        print("Response JSON:", await resp.text())

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_rates())

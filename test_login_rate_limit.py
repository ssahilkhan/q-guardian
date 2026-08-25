import asyncio
from httpx import ASGITransport, AsyncClient
from q_guardian.api.app import create_app


async def test():
    app = create_app()
    transport = ASGITransport(app=app)
    headers = {"X-Forwarded-For": "10.1.2.3"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as ac:
        for i in range(7):
            resp = await ac.post(
                "/api/v1/auth/login", json={"username": "testuser", "password": "wrong"}
            )
            if resp.status_code == 429:
                print(f"Attempt {i + 1}: 429 Retry-After: {resp.headers.get('Retry-After')}")
            else:
                print(f"Attempt {i + 1}: {resp.status_code}")


asyncio.run(test())

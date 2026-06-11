import asyncio
import httpx

async def check_port(port):
    async with httpx.AsyncClient(timeout=3) as c:
        for path in ['/', '/sse']:
            url = f'http://localhost:{port}{path}'
            try:
                r = await c.get(url)
                ct = r.headers.get('content-type','')
                print(f'http://localhost:{port}{path}: {r.status_code} [{ct}] {r.text[:120]!r}')
            except httpx.ReadTimeout:
                print(f'http://localhost:{port}{path}: STREAMING (timeout = SSE open connection)')
            except Exception as e:
                print(f'http://localhost:{port}{path}: ERROR {type(e).__name__}: {e}')

async def main():
    tasks = [check_port(p) for p in range(8001,8006)]
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    asyncio.run(main())

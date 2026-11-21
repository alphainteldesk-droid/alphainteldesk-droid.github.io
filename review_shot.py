"""Throwaway (Nov 21): load competitor pages in a real browser, save screenshots + visible text."""
import asyncio, os
from playwright.async_api import async_playwright
URLS = [("arb", "https://arbprediction.com/")]
async def main():
    os.makedirs("out", exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for name, url in URLS:
            for vw, tag in [(1440, "desk"), (390, "phone")]:
                pg = await b.new_page(viewport={"width": vw, "height": 900})
                try:
                    await pg.goto(url, wait_until="networkidle", timeout=60000)
                except Exception as e:
                    print("goto", url, e)
                await pg.wait_for_timeout(6000)
                await pg.screenshot(path="out/%s-%s.png" % (name, tag), full_page=True)
                if tag == "desk":
                    txt = await pg.evaluate("() => document.body.innerText")
                    links = await pg.evaluate("() => [...document.querySelectorAll('a')].map(a => (a.innerText.trim().slice(0,40) + ' -> ' + a.href)).slice(0,120)")
                    open("out/%s.txt" % name, "w").write(txt + "\n\n=== LINKS\n" + "\n".join(links))
                    # click through internal nav pages
                    hrefs = await pg.evaluate("() => [...new Set([...document.querySelectorAll('a')].map(a => a.href).filter(h => h.startsWith(location.origin) && !h.includes('#')))].slice(0,8)")
                    for i, h in enumerate(hrefs):
                        q = await b.new_page(viewport={"width": 1440, "height": 900})
                        try:
                            await q.goto(h, wait_until="networkidle", timeout=45000); await q.wait_for_timeout(4000)
                            await q.screenshot(path="out/%s-p%d.png" % (name, i), full_page=True)
                            t = await q.evaluate("() => document.body.innerText")
                            open("out/%s-p%d.txt" % (name, i), "w").write(h + "\n\n" + t)
                        except Exception as e:
                            print("sub", h, e)
                        await q.close()
                await pg.close()
        await b.close()
asyncio.run(main())

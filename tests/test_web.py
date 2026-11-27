"""Bulut yüz: sayfa hatasız açılır, olaylar yüzü değiştirir, altyazı bulutu kaydırmaz.

Playwright + Chromium yoksa atlanır.
"""

import asyncio

import pytest

pw = pytest.importorskip("playwright.async_api")

from nimbus.web import WebGovde  # noqa: E402


async def _sayfa(port):
    g = WebGovde(port=port, tarayici_ac=False)
    await g.baslat()
    p = await pw.async_playwright().start()
    try:
        b = await p.chromium.launch()
    except Exception as e:
        await p.stop()
        pytest.skip(f"Chromium yok: {e}")
    sayfa = await b.new_page(viewport={"width": 1100, "height": 760})
    hatalar = []
    sayfa.on("pageerror", lambda e: hatalar.append(str(e)))
    await sayfa.goto(f"http://localhost:{port}")
    await asyncio.sleep(0.8)
    return g, p, b, sayfa, hatalar


def test_yuz_olaylari():
    async def calis():
        g, p, b, s, hatalar = await _sayfa(8791)
        assert "uyku" in await s.evaluate("document.body.className")
        g.durum("sohbet"); g.agiz(1.0); g.jest("gul")
        await asyncio.sleep(0.4)
        sinif = await s.evaluate("document.body.className")
        ry = float(await s.evaluate("document.getElementById('agiz').getAttribute('ry')"))
        assert "uyku" not in sinif and "gul" in sinif and ry > 20
        assert await s.inner_text("#baglanti") == "● canlı"
        await b.close(); await p.stop()
        assert not hatalar
    asyncio.run(calis())


def test_uzun_altyazi_bulutu_kaydirmaz():
    async def calis():
        g, p, b, s, hatalar = await _sayfa(8792)
        g.durum("sohbet"); await asyncio.sleep(0.3)
        await s.evaluate("document.getElementById('bulut-grubu').style.animation='none'")
        kutu = "JSON.stringify(document.getElementById('sahne').getBoundingClientRect())"
        once = await s.evaluate(kutu)
        g.altyazi("nimbus", "Çok uzun bir cümle " * 25)
        await asyncio.sleep(0.3)
        assert await s.evaluate(kutu) == once
        await b.close(); await p.stop()
    asyncio.run(calis())

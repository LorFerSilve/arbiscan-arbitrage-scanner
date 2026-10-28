"""Real Chromium acceptance for Phase 20.3 (development-only dependency).

Run:
  uv run --with playwright==1.56.0 python -m playwright install chromium
  uv run --with playwright==1.56.0 python browser_e2e/acceptance.py

No external provider requests. The complete browser/server is localhost-only.
Tests use the actual Python API, actual HTML/JS/CSS and a real Chromium engine.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Thread

from playwright.sync_api import Page, sync_playwright

from arbiscan.api.http import create_local_http_server
from arbiscan.api.service import ArbiScanApi
from arbiscan.api.synthetic import SyntheticApiDataSource


@contextmanager
def local_server(*, demo: bool) -> Iterator[str]:
    api = ArbiScanApi(SyntheticApiDataSource(demo=demo), version="phase20-e2e")
    with create_local_http_server(
        api=api, mode="synthetic" if demo else "empty", version="phase20-e2e", port=0
    ) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join(timeout=3)


def expect(condition: bool, description: str) -> None:
    if not condition:
        raise AssertionError(description)


def test_demo(page: Page, base: str) -> None:
    page.goto(base, wait_until="networkidle")
    page.locator("#opportunity-rows .details-button").wait_for()
    expect("DEMO" in page.locator("#notice-tag").inner_text(), "demo marker absent")
    expect(page.locator("#metric-actionable").inner_text() == "0", "actionable count > 0")
    expect(page.locator("#metric-demo").inner_text() == "1", "demo opportunity missing")
    expect(page.locator("#opportunity-rows tr").count() == 1, "expected one demo row")
    expect("Example FC" in page.locator("#opportunity-rows").inner_text(), "wrong fixture")

    page.locator("#search").fill("never-found")
    expect(page.locator("#opportunity-empty").is_visible(), "no-results state missing")
    expect(page.locator("#opportunity-rows tr").count() == 0, "search didn't filter")
    page.locator("#search").fill("Example FC")
    expect(page.locator("#opportunity-rows tr").count() == 1, "search didn't restore row")
    page.locator("#min-roi").fill("20")
    expect(page.locator("#opportunity-empty").is_visible(), "minimum ROI not applied")
    page.locator("#min-roi").fill("0")
    page.locator("#provider-filter").select_option("synthetic-source-a")
    expect(page.locator("#opportunity-rows tr").count() == 1, "provider filter failed")
    page.locator("#provider-filter").select_option("")
    page.locator("#sport-filter").select_option("football")
    expect(page.locator("#opportunity-rows tr").count() == 1, "sport filter failed")

    page.locator("#opportunity-rows button").click()
    page.locator("#detail-drawer").wait_for(state="visible")
    drawer = page.locator("#detail-drawer")
    drawer.get_by_text("Python-berekening", exact=False).wait_for()
    detail = drawer.inner_text()
    for term in (
        "Python-berekening",
        "100.00",
        "Modelwinst",
        "Synthetisch",
        "Inzet per uitkomst",
        "Modelaannames",
        "EUR",
    ):
        expect(term.lower() in detail.lower(), f"stake detail missing {term}")
    expect(drawer.locator(".drawer-leg").count() >= 6, "quote+stake legs missing")
    expect("Niet beschikbaar" in detail, "missing evidence status not displayed")
    expect("NIET UITVOERBAAR" in detail, "unapproved demo described as actionable")
    page.keyboard.press("Escape")
    expect(drawer.is_hidden(), "Escape didn't close drawer")
    page.locator("#refresh").click()
    page.wait_for_function("!document.querySelector('#refresh').disabled")
    expect(page.locator("#opportunity-rows tr").count() == 1, "refresh lost demo data")

    # Responsive/mobile checks use the real browser's layout engine.
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.locator("#welcome-title").is_visible(), "mobile hero not visible")
    expect(
        page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"),
        "mobile page causes unwanted horizontal body overflow",
    )
    page.locator("#opportunity-rows button").click()
    expect(drawer.is_visible(), "mobile detail drawer inaccessible")
    page.locator("#close-detail").click()
    expect(drawer.is_hidden(), "mobile close button didn't work")


def test_empty(page: Page, base: str) -> None:
    page.goto(base, wait_until="networkidle")
    page.wait_for_function("document.querySelector('#notice-tag').textContent.includes('EMPTY')")
    expect("EMPTY" in page.locator("#notice-tag").inner_text(), "empty mode not marked")
    expect(page.locator("#metric-actionable").inner_text() == "0", "empty shows live signal")
    expect(page.locator("#opportunity-rows tr").count() == 0, "empty has invented rows")
    expect(page.locator("#opportunity-empty").is_visible(), "empty-state message absent")
    expect(
        "Geen providers" in page.locator("#provider-list").inner_text(),
        "empty providers shown incorrectly",
    )


def test_refresh_error(page: Page, base: str) -> None:
    page.goto(base, wait_until="networkidle")
    page.locator("#opportunity-rows button").wait_for()
    # Simulate a failed API page. No stale, previously loaded opportunity
    # may remain on the screen after a refresh failure.
    page.route("**/api/v1/events?*", lambda route: route.abort())
    page.locator("#refresh").click()
    page.locator("#toast").wait_for(state="visible")
    expect("OFFLINE" in page.locator("#notice-tag").inner_text(), "error mode not marked")
    expect(page.locator("#opportunity-rows tr").count() == 0, "stale signal still visible")
    expect(page.locator("#opportunity-empty").is_visible(), "empty/error state not displayed")


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            with local_server(demo=True) as base:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                observed: list[str] = []
                page.on("pageerror", lambda exc: observed.append(str(exc)))
                page.on(
                    "request",
                    lambda req: (
                        observed.append("unexpected remote origin: " + req.url)
                        if not req.url.startswith(base + "/")
                        else None
                    ),
                )
                test_demo(page, base)
                test_refresh_error(page, base)
                expect(not observed, f"browser errors or external requests: {observed}")
                page.close()
            with local_server(demo=False) as base:
                page = browser.new_page(viewport={"width": 390, "height": 844})
                test_empty(page, base)
                page.close()
        finally:
            browser.close()
    print(
        "Phase 20.3 real Chromium: demo, search/filters, Python stakes, empty, error, mobile PASS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

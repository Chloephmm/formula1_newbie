"""Hosted browser acceptance for an already-open saved prediction page.

Run only after deployment authorization while another process publishes the supplied
``after`` fixture. The script never reloads or clicks the page; it proves the timed
Streamlit fragment changes mode and prediction ID together in one browser session.
"""
from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--before-id", required=True)
    parser.add_argument("--after-id", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=90)
    args = parser.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Install Playwright and its Chromium runtime for the hosted acceptance check."
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(args.url, wait_until="networkidle")
        page.get_by_text(args.before_id, exact=False).wait_for()
        page.get_by_text(args.after_id, exact=False).wait_for(
            timeout=args.timeout_seconds * 1000
        )
        page.get_by_text("Mode: Actual qualifying", exact=False).wait_for()
        if page.get_by_text(args.before_id, exact=False).count():
            raise AssertionError("old prediction ID remained after the fragment update")
        browser.close()


if __name__ == "__main__":
    main()

"""Render Designer's HTML mockups into PNG using headless chromium."""
from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

from loguru import logger
from playwright.async_api import async_playwright


MOCKUPS_DIR = Path("/app/mockups/rendered")
MOCKUPS_DIR.mkdir(parents=True, exist_ok=True)


async def render_html_to_png(html: str, *, width: int, label: str) -> Path:
    """Render an HTML string to PNG at the specified viewport width.

    width=375 → mobile (iPhone-ish viewport, 812 height)
    width=1280 → desktop / web
    """
    out_path = MOCKUPS_DIR / f"{label}_{uuid4().hex[:8]}.png"
    height = 812 if width <= 480 else 800

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        try:
            ctx = await browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=2,
            )
            page = await ctx.new_page()
            await page.set_content(html, wait_until="networkidle")
            # Give fonts a moment to load even after networkidle
            await asyncio.sleep(0.8)
            await page.screenshot(path=str(out_path), full_page=True)
        finally:
            await browser.close()

    logger.info("Rendered mockup → {}", out_path)
    return out_path


def extract_html_blocks(markdown_text: str) -> dict[str, str]:
    """Parse the Designer's Markdown output and pull out the three possible mockup blocks.

    Returns a dict keyed by surface name: 'web', 'mobile', 'landing'.
    """
    sections = {
        "web":     "## Mockup — PWA / web",
        "mobile":  "## Mockup — Mobile",
        "landing": "## Mockup — Landing",
    }
    out: dict[str, str] = {}

    for key, header in sections.items():
        if header not in markdown_text:
            continue
        chunk = markdown_text.split(header, 1)[1]
        # next ## section bounds the chunk
        next_idx = chunk.find("\n## ")
        if next_idx > 0:
            chunk = chunk[:next_idx]
        # extract first ```html fenced block
        fence = "```html"
        if fence not in chunk:
            continue
        body = chunk.split(fence, 1)[1].split("```", 1)[0].strip()
        out[key] = body
    return out


async def render_all_mockups(markdown_text: str) -> dict[str, Path]:
    """Render every mockup block found in the Designer's output.

    Returns {surface: path_to_png}.
    """
    blocks = extract_html_blocks(markdown_text)
    results: dict[str, Path] = {}
    widths = {"web": 1280, "mobile": 375, "landing": 1280}
    for surface, html in blocks.items():
        try:
            png = await render_html_to_png(html, width=widths[surface], label=surface)
            results[surface] = png
        except Exception as e:
            logger.exception("Render failed for {}: {}", surface, e)
    return results

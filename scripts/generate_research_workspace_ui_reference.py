"""Generate a Public-Core-safe synthetic Research Workspace design reference.

No real usernames, run IDs, configs, or production metrics.
Output: docs/design/research-workspace-hyperliquid-reference.png
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1440, 900
BG = (6, 14, 20)
PANEL = (10, 21, 29)
BORDER = (36, 52, 64)
MINT = (66, 217, 139)
TEXT = (237, 244, 241)
MUTED = (109, 122, 132)
WARN = (217, 167, 46)
NEG = (240, 82, 82)


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 14)
        font_sm = ImageFont.truetype("arial.ttf", 11)
        font_mono = ImageFont.truetype("consola.ttf", 11)
        font_title = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
        font_sm = font
        font_mono = font
        font_title = font

    def rect(xy: tuple[int, int, int, int], fill=None, outline=BORDER, width: int = 1) -> None:
        d.rectangle(xy, fill=fill, outline=outline, width=width)

    # Topbar
    rect((0, 0, W - 1, 44), fill=PANEL)
    d.text((14, 14), "SAVE-MONEY BOT", fill=TEXT, font=font_sm)
    rect((160, 10, 290, 34), fill=BG, outline=BORDER)
    d.text((172, 15), "Monitor", fill=MUTED, font=font_sm)
    d.text((230, 15), "Research", fill=MINT, font=font_sm)
    d.text((W - 120, 15), "demo", fill=MUTED, font=font_sm)
    d.text((W - 70, 15), "Logout", fill=MUTED, font=font_sm)

    # Ticker
    rect((0, 44, W - 1, 76), fill=PANEL)
    d.text(
        (14, 54),
        "Universe  BTC  Nicht verfuegbar   ETH  Nicht verfuegbar   SOL  Nicht verfuegbar",
        fill=MUTED,
        font=font_sm,
    )

    # Sidebar
    side_w = 200
    rect((0, 76, side_w, H - 1), fill=PANEL)
    d.text((14, 90), "Research Workspace", fill=TEXT, font=font_title)
    d.text((14, 114), "Synthetic wireframe — no real runs", fill=MUTED, font=font_sm)
    for i, label in enumerate(
        [
            "Overview",
            "Strategien",
            "Experiments",
            "Neues Experiment",
            "Vergleich",
            "Robustheit",
            "Validierung",
        ]
    ):
        y = 150 + i * 28
        fill = MINT if label == "Overview" else MUTED
        if label == "Overview":
            rect((8, y - 4, side_w - 8, y + 18), fill=(26, 77, 50))
        d.text((16, y), label, fill=fill, font=font_sm)

    main_x = side_w + 12
    rect((main_x, 88, W - 12, 200), fill=PANEL)
    d.text((main_x + 12, 100), "Executive Gates (synthetic)", fill=TEXT, font=font)
    for i, (lab, val, col) in enumerate(
        [
            ("Integrity", "PASS", MINT),
            ("Critical Gates", "Nicht verfuegbar", MUTED),
            ("Evidence", "Nicht verfuegbar", MUTED),
            ("Decision", "pending", WARN),
        ]
    ):
        x = main_x + 12 + i * 280
        d.text((x, 140), lab.upper(), fill=MUTED, font=font_sm)
        d.text((x, 162), val, fill=col, font=font_mono)

    rect((main_x, 212, W - 12, 520), fill=PANEL)
    d.text((main_x + 12, 224), "Regime Scorecard (placeholder)", fill=TEXT, font=font)
    headers = ["Regime", "Trades", "Net PnL", "Max DD", "Label"]
    for i, h in enumerate(headers):
        d.text((main_x + 20 + i * 200, 256), h, fill=MUTED, font=font_sm)
    d.line([(main_x + 12, 276), (W - 24, 276)], fill=BORDER)
    for r, row in enumerate(
        [
            ("trend_up", "n/a", "Nicht verfuegbar", "Nicht verfuegbar", "insufficient"),
            ("range", "n/a", "Nicht verfuegbar", "Nicht verfuegbar", "insufficient"),
            ("trend_down", "n/a", "Nicht verfuegbar", "Nicht verfuegbar", "insufficient"),
        ]
    ):
        y = 290 + r * 36
        for i, cell in enumerate(row):
            col = MUTED if cell in ("n/a", "Nicht verfuegbar", "insufficient") else TEXT
            d.text((main_x + 20 + i * 200, y), cell, fill=col, font=font_mono)

    rect((main_x, 532, W - 12, 820), fill=PANEL)
    d.text((main_x + 12, 544), "Analytics placeholders", fill=TEXT, font=font)
    rect((main_x + 20, 580, main_x + 560, 790), fill=BG, outline=BORDER)
    d.text((main_x + 36, 600), "Equity vs Benchmark", fill=MUTED, font=font_sm)
    d.text((main_x + 36, 680), "Nicht verfuegbar", fill=MUTED, font=font_mono)
    rect((main_x + 580, 580, W - 32, 790), fill=BG, outline=BORDER)
    d.text((main_x + 596, 600), "Underwater Drawdown", fill=MUTED, font=font_sm)
    d.text((main_x + 596, 680), "Nicht verfuegbar", fill=NEG, font=font_mono)

    d.text(
        (main_x + 12, H - 40),
        "SYNTHETIC DESIGN REFERENCE — Public Core safe — no production metrics, no private edge",
        fill=WARN,
        font=font_sm,
    )
    d.text(
        (main_x + 12, H - 22),
        "docs/design/research-workspace-hyperliquid-reference.png | Issue #298",
        fill=MUTED,
        font=font_sm,
    )

    out = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "design"
        / "research-workspace-hyperliquid-reference.png"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

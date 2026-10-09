"""Generate the native TabBar's local, transparent line icons."""

from pathlib import Path

from PIL import Image, ImageDraw

TARGET = Path(__file__).resolve().parents[2] / "apps/miniapp/src/assets"


def render(name: str, color: str, active: bool) -> None:
    image = Image.new("RGBA", (192, 192))
    draw = ImageDraw.Draw(image)

    def line(points: list[tuple[int, int]]) -> None:
        draw.line([(x * 4, y * 4) for x, y in points], fill=color, width=8, joint="curve")

    def box(coords: tuple[int, int, int, int], radius: int = 0) -> None:
        draw.rounded_rectangle(tuple(n * 4 for n in coords), radius=radius * 4, outline=color, width=8)

    if name == "home":
        line([(7, 22), (24, 7), (41, 22)])
        line([(12, 20), (12, 40), (20, 40), (20, 29), (28, 29), (28, 40), (36, 40), (36, 20)])
    elif name == "category":
        for x in (8, 27):
            for y in (8, 27):
                box((x, y, x + 13, y + 13), 2)
    elif name == "cart":
        line([(5, 9), (11, 9), (16, 32), (36, 32), (41, 16), (13, 16)])
        for x in (19, 34):
            box((x - 2, 38, x + 2, 42), 2)
    elif name == "account":
        draw.ellipse((68, 24, 124, 80), outline=color, width=8)
        draw.arc((36, 96, 156, 192), 180, 360, fill=color, width=8)
        line([(9, 36), (9, 41), (39, 41), (39, 36)])
    image.resize((48, 48), Image.Resampling.LANCZOS).save(TARGET / f"tab-{name}{'-active' if active else ''}.png")


if __name__ == "__main__":
    TARGET.mkdir(parents=True, exist_ok=True)
    for icon in ("home", "category", "cart", "account"):
        render(icon, "#475467", False)
        render(icon, "#B42318", True)

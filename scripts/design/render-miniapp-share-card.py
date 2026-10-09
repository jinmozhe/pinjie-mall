"""Render a fixed 5:4 share cover that contains no account data or reward claims."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
image = Image.new("RGB", (750, 600), "#F7F8FA")
draw = ImageDraw.Draw(image)
font_path = Path("C:/Windows/Fonts/msyh.ttc")
title = ImageFont.truetype(str(font_path), 64)
body = ImageFont.truetype(str(font_path), 32)
draw.rounded_rectangle((48, 48, 702, 552), radius=20, fill="#FFFFFF")
draw.rectangle((96, 112, 156, 120), fill="#B42318")
draw.text((96, 160), "拼捷商城", font=title, fill="#1D2939")
draw.text((96, 276), "邀你一起逛商城", font=body, fill="#475467")
draw.rounded_rectangle((96, 382, 654, 470), radius=12, fill="#B42318")
draw.text((280, 402), "浏览商品", font=body, fill="#FFFFFF")
target = ROOT / "apps/miniapp/src/assets/share-mall.png"
image.save(target, optimize=True)
print(f"SHARE_COVER_OK {image.size[0]}x{image.size[1]}")

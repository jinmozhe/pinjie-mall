"""Draw the initial visual proposal; this is not a miniapp or HTML prototype."""

from pathlib import Path
import argparse
import os

from PIL import Image, ImageDraw, ImageFont, ImageFilter


ROOT = Path(__file__).resolve().parent
W, H = 750, 1624
C = {
    'primary': '#B42318', 'soft': '#FFF1EF', 'background': '#F7F8FA',
    'surface': '#FFFFFF', 'text': '#1D2939', 'secondary': '#475467',
    'disabled': '#98A2B3', 'border': '#E4E7EC',
}
FONTS = {}
REGULAR = BOLD = None


def font(size, bold=False):
    key = (size, bold)
    if key not in FONTS:
        FONTS[key] = ImageFont.truetype(str(BOLD if bold else REGULAR), size)
    return FONTS[key]


def text(im, xy, value, size=28, color='text', bold=False, anchor='lt'):
    ImageDraw.Draw(im).text(xy, value, font=font(size, bold),
                           fill=C.get(color, color), anchor=anchor)


def box(im, xy, fill='surface', radius=20, outline=None, width=2):
    ImageDraw.Draw(im).rounded_rectangle(xy, radius=radius, fill=C.get(fill, fill),
                                        outline=C.get(outline, outline), width=width)


def line(im, pts, color='border', width=2):
    ImageDraw.Draw(im).line(pts, fill=C.get(color, color), width=width, joint='curve')


def icon(im, x, y, kind, color='secondary', size=40):
    d = ImageDraw.Draw(im)
    stroke = C.get(color, color)
    s = size / 40
    def p(a, b):
        return (int(x + a * s), int(y + b * s))
    if kind == 'home':
        d.line([p(3, 19), p(20, 4), p(37, 19)], fill=stroke, width=4)
        d.line([p(8, 17), p(8, 36), p(16, 36), p(16, 25), p(24, 25),
                p(24, 36), p(32, 36), p(32, 17)], fill=stroke, width=4)
    elif kind == 'grid':
        for a, b in [(4, 4), (25, 4), (4, 25), (25, 25)]:
            d.rounded_rectangle([p(a, b), p(a + 11, b + 11)], radius=2,
                                outline=stroke, width=3)
    elif kind == 'cart':
        d.line([p(2, 5), p(7, 5), p(11, 27), p(32, 27), p(37, 11), p(8, 11)],
               fill=stroke, width=3)
        for a in [14, 29]:
            d.ellipse([p(a - 3, 32), p(a + 3, 38)], outline=stroke, width=3)
    elif kind == 'user':
        d.ellipse([p(13, 3), p(27, 17)], outline=stroke, width=3)
        d.arc([p(5, 22), p(35, 48)], 180, 360, fill=stroke, width=3)
        d.line([p(5, 35), p(35, 35)], fill=stroke, width=3)
    elif kind == 'shirt':
        d.line([p(13, 5), p(4, 9), p(0, 20), p(9, 24), p(12, 18),
                p(12, 36), p(29, 36), p(29, 18), p(32, 24), p(40, 20),
                p(36, 9), p(27, 5)], fill=stroke, width=3)
        d.arc([p(13, 1), p(27, 14)], 0, 180, fill=stroke, width=3)
    elif kind == 'shoe':
        d.line([p(5, 8), p(5, 26), p(20, 26), p(29, 30), p(36, 30),
                p(36, 36), p(3, 36), p(3, 25)], fill=stroke, width=3)
    elif kind == 'bag':
        d.rounded_rectangle([p(6, 13), p(34, 37)], radius=3, outline=stroke, width=3)
        d.arc([p(12, 0), p(28, 26)], 180, 360, fill=stroke, width=3)
    elif kind == 'phone':
        d.rounded_rectangle([p(10, 2), p(30, 38)], radius=4, outline=stroke, width=3)
        d.line([p(16, 32), p(24, 32)], fill=stroke, width=3)
    elif kind == 'back':
        d.line([p(27, 4), p(11, 20), p(27, 36)], fill=stroke, width=3)
    elif kind == 'next':
        d.line([p(14, 9), p(25, 20), p(14, 31)], fill=stroke, width=3)
    elif kind == 'close':
        d.line([p(9, 9), p(31, 31)], fill=stroke, width=3)
        d.line([p(31, 9), p(9, 31)], fill=stroke, width=3)


def shell(title, back=False):
    im = Image.new('RGB', (W, H), C['background'])
    box(im, (0, 0, W, 174), radius=0)
    text(im, (38, 20), '9:41', 28, bold=True)
    d = ImageDraw.Draw(im)
    for j in range(4):
        d.rectangle((596 + j * 9, 43 - j * 5, 601 + j * 9, 45), fill=C['text'])
    d.arc((643, 23, 671, 48), 205, 335, fill=C['text'], width=3)
    d.rounded_rectangle((683, 26, 716, 43), radius=4, outline=C['text'], width=2)
    d.rectangle((687, 30, 708, 39), fill=C['text'])
    text(im, (W / 2, 111), title, 32, bold=True, anchor='mm')
    if back:
        icon(im, 24, 90, 'back')
    box(im, (563, 80, 718, 140), outline='border', radius=30)
    for j in range(3):
        d.ellipse((587 + 13 * j, 107, 593 + 13 * j, 113), fill=C['text'])
    line(im, [(641, 94), (641, 126)])
    d.ellipse((664, 97, 690, 123), outline=C['text'], width=3)
    d.ellipse((673, 106, 681, 114), fill=C['text'])
    line(im, [(0, 173), (W, 173)], width=1)
    return im


def home_indicator(im):
    box(im, (251, H - 25, 499, H - 15), 'text', radius=5)


def tabbar(im, active='home'):
    box(im, (0, 1488, W, H), radius=0)
    line(im, [(0, 1488), (W, 1488)], width=1)
    for i, (kind, label) in enumerate([('home', '首页'), ('grid', '分类'),
                                       ('cart', '购物车'), ('user', '我的')]):
        cx = int((i + .5) * W / 4)
        color = 'primary' if active == kind else 'secondary'
        icon(im, cx - 24, 1507, kind, color, 48)
        text(im, (cx, 1570), label, 24, color, anchor='mm')
    home_indicator(im)


def garment(size, shade='white', bag=False):
    w, h = size
    im = Image.new('RGB', size, '#F0EEE9')
    shadow = Image.new('RGBA', size)
    sd = ImageDraw.Draw(shadow)
    sd.ellipse((w * .22, h * .81, w * .80, h * .88), fill=(38, 37, 34, 36))
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(2, w / 45)))
    im.paste(shadow, (0, 0), shadow)
    d = ImageDraw.Draw(im)
    def q(x, y):
        return (int(w * x), int(h * y))
    if bag:
        d.arc([q(.34, .10), q(.66, .54)], 180, 360, fill='#BAAC95', width=max(3, w // 50))
        d.polygon([q(.25, .33), q(.75, .33), q(.81, .82), q(.19, .82)],
                  fill='#DED3BE', outline='#BFAF93')
        d.line([q(.30, .35), q(.25, .78)], fill='#C4B69B', width=2)
        d.line([q(.70, .35), q(.75, .78)], fill='#F5EDD9', width=3)
    else:
        colors = {'white': ('#FAFAF8', '#D5D4CF', '#E7E6E0'),
                  'black': ('#343638', '#242628', '#484A4C'),
                  'gray': ('#A6A7A6', '#868886', '#B7B8B7')}
        fill, edge, crease = colors[shade]
        pts = [q(.34, .19), q(.18, .27), q(.07, .47), q(.23, .55),
               q(.31, .42), q(.28, .83), q(.72, .83), q(.69, .42),
               q(.77, .55), q(.93, .47), q(.82, .27), q(.66, .19)]
        d.polygon(pts, fill=fill, outline=edge, width=max(1, w // 300))
        d.ellipse([q(.41, .155), q(.59, .255)], fill='#F0EEE9', outline=edge, width=2)
        for coords in [(.33, .43, .35, .77), (.67, .43, .65, .77),
                       (.39, .36, .40, .73), (.29, .79, .71, .79)]:
            d.line([q(coords[0], coords[1]), q(coords[2], coords[3])],
                   fill=crease, width=max(1, w // 220))
    return im


def product_card(im, x, y, label, price, shade='white', bag=False):
    box(im, (x, y, x + 331, y + 484), radius=20)
    photo = garment((331, 331), shade, bag)
    mask = Image.new('L', photo.size)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 330, 351), radius=20, fill=255)
    im.paste(photo, (x, y), mask)
    text(im, (x + 20, y + 351), label, 28, bold=True)
    text(im, (x + 20, y + 395), '实物商品 · 设计示例', 24, 'secondary')
    text(im, (x + 20, y + 436), '¥', 26, 'primary', bold=True)
    text(im, (x + 47, y + 430), price, 36, 'primary', bold=True)


def home():
    im = shell('拼捷商城')
    text(im, (32, 207), '商城商品', 36, bold=True)
    text(im, (32, 264), '浏览分类，选择适合你的商品', 28, 'secondary')
    box(im, (32, 328, 718, 490), radius=20)
    for i, (kind, label) in enumerate([('shirt', '服饰'), ('shoe', '鞋靴'),
                                       ('bag', '家居'), ('phone', '数码')]):
        cx = 118 + i * 171
        box(im, (cx - 36, 347, cx + 36, 419), '#F7F6F3', radius=36)
        icon(im, cx - 20, 363, kind)
        text(im, (cx, 454), label, 28, anchor='mm')
    text(im, (32, 520), '全部商品', 32, bold=True)
    product_card(im, 32, 581, '基础圆领短袖 · 白色', '129.00')
    product_card(im, 387, 581, '基础圆领短袖 · 黑色', '129.00', 'black')
    product_card(im, 32, 1089, '基础圆领短袖 · 灰色', '129.00', 'gray')
    product_card(im, 387, 1089, '日常帆布手提袋', '89.00', bag=True)
    tabbar(im)
    return im


def detail():
    im = shell('商品详情', True)
    im.paste(garment((750, 650)), (0, 174))
    box(im, (641, 754, 718, 798), '#FFFFFF', radius=22)
    text(im, (679, 776), '1 / 3', 24, anchor='mm')
    box(im, (0, 824, W, 1112), radius=0)
    text(im, (32, 856), '基础圆领短袖', 36, bold=True)
    text(im, (32, 912), '实物商品 · 多规格', 28, 'secondary')
    text(im, (32, 974), '¥', 28, 'primary', bold=True)
    text(im, (61, 961), '129.00', 44, 'primary', bold=True)
    text(im, (32, 1040), '参考价，成交金额以结算报价为准', 24, 'secondary')
    box(im, (32, 1136, 718, 1240), radius=20)
    text(im, (56, 1172), '规格', 28, bold=True)
    text(im, (160, 1172), '选择颜色、尺码', 28, 'secondary')
    icon(im, 654, 1167, 'next')
    box(im, (32, 1264, 718, 1470), radius=20)
    text(im, (56, 1294), '商品说明', 32, bold=True)
    text(im, (56, 1350), '基础圆领款式，规格与材质详见商品资料。', 26, 'secondary')
    text(im, (56, 1395), '下滑查看完整说明、详情图集与评价', 24, 'secondary')
    box(im, (0, 1488, W, H), radius=0)
    line(im, [(0, 1488), (W, 1488)], width=1)
    icon(im, 44, 1508, 'home')
    icon(im, 138, 1508, 'cart')
    text(im, (64, 1570), '首页', 24, anchor='mm')
    text(im, (158, 1570), '购物车', 24, anchor='mm')
    box(im, (232, 1496, 463, 1584), 'surface', 12, 'primary')
    text(im, (347, 1540), '加入购物车', 28, 'primary', True, 'mm')
    box(im, (487, 1496, 718, 1584), 'primary', 12)
    text(im, (602, 1540), '立即购买', 28, 'surface', True, 'mm')
    # Controls end before the indicator; bottom safe-area remains visible.
    home_indicator(im)
    return im


def sku():
    im = detail()
    overlay = Image.new('RGBA', im.size, (0, 0, 0, 105))
    im = Image.alpha_composite(im.convert('RGBA'), overlay).convert('RGB')
    box(im, (0, 554, W, H + 24), radius=24)
    icon(im, 646, 580, 'close')
    thumb = garment((160, 160))
    im.paste(thumb, (32, 602))
    text(im, (216, 602), '基础圆领短袖', 32, bold=True)
    text(im, (216, 656), '¥129.00', 44, 'primary', True)
    text(im, (216, 717), '已选：白色 / M', 26, 'secondary')
    line(im, [(32, 794), (718, 794)])
    text(im, (32, 834), '颜色', 28, bold=True)
    for x, label, selected in [(32, '白色', True), (218, '黑色', False), (404, '灰色', False)]:
        box(im, (x, 886, x + 162, 974), 'soft' if selected else 'background',
            12, 'primary' if selected else None)
        text(im, (x + 81, 930), label, 28, 'primary' if selected else 'text', selected, 'mm')
    text(im, (32, 1026), '尺码', 28, bold=True)
    for x, label in [(32, 'S'), (218, 'M'), (404, 'L')]:
        selected = label == 'M'
        box(im, (x, 1078, x + 162, 1166), 'soft' if selected else 'background',
            12, 'primary' if selected else None)
        text(im, (x + 81, 1122), label, 28, 'primary' if selected else 'text', selected, 'mm')
    box(im, (590, 1078, 718, 1166), 'background', 12)
    text(im, (654, 1102), 'XL', 26, 'disabled', anchor='mm')
    text(im, (654, 1138), '已停用', 24, 'secondary', anchor='mm')
    line(im, [(32, 1210), (718, 1210)])
    text(im, (32, 1272), '购买数量', 28, bold=True)
    box(im, (430, 1244, 718, 1332), 'surface', 12, 'border')
    line(im, [(526, 1244), (526, 1332)])
    line(im, [(622, 1244), (622, 1332)])
    text(im, (478, 1288), '−', 32, 'disabled', anchor='mm')
    text(im, (574, 1288), '1', 28, bold=True, anchor='mm')
    text(im, (670, 1288), '+', 32, anchor='mm')
    text(im, (32, 1370), '数量与可售状态以服务端校验为准', 24, 'secondary')
    line(im, [(0, 1460), (W, 1460)], width=1)
    box(im, (32, 1488, 718, 1576), 'primary', 12)
    text(im, (375, 1532), '确认加入购物车', 28, 'surface', True, 'mm')
    home_indicator(im)
    return im


def main():
    global REGULAR, BOLD
    parser = argparse.ArgumentParser(description=__doc__)
    windows_fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    parser.add_argument('--font', type=Path, default=windows_fonts / 'msyh.ttc')
    parser.add_argument('--bold-font', type=Path, default=windows_fonts / 'msyhbd.ttc')
    args = parser.parse_args()
    REGULAR, BOLD = args.font, args.bold_font
    if not REGULAR.is_file() or not BOLD.is_file():
        raise FileNotFoundError('Pass installed Chinese font paths via --font and --bold-font')
    output = ROOT / 'screenshots'
    names = ['home-v1.png', 'product-detail-v1.png', 'sku-sheet-v1.png']
    images = [home(), detail(), sku()]
    if any((output / name).exists() for name in names + ['overview-v1.png']):
        raise FileExistsError('Version outputs already exist; create a new version explicitly')
    output.mkdir(parents=True, exist_ok=True)
    for name, im in zip(names, images):
        im.save(output / name)
    board = Image.new('RGB', (2446, 1904), '#ECEDEA')
    text(board, (50, 42), '拼捷商城 / 核心页面视觉提案', 42, bold=True)
    text(board, (50, 108), 'V1 · 待确认 · 商品、价格、规格与分类均为设计示例 · 非微信运行截图', 28, 'secondary')
    labels = ['01  首页 / 公开浏览', '02  商品详情 / 信息与购买', '03  SKU / 规格与数量']
    for i, (label, im) in enumerate(zip(labels, images)):
        x = 50 + i * 798
        text(board, (x, 178), label, 28, bold=True)
        board.paste(im, (x, 230))
    board.save(output / 'overview-v1.png')
    for name in names + ['overview-v1.png']:
        with Image.open(output / name) as im:
            im.verify()
        print(name)


if __name__ == '__main__':
    main()

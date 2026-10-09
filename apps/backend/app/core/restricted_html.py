import re
from html import escape

import html5lib

ALLOWED_TAGS = frozenset(
    {"p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "span", "font", *(f"h{i}" for i in range(1, 7))}
)


def _color(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})", value):
        return value.lower()
    match = re.fullmatch(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", value)
    if match and all(int(v) <= 255 for v in match.groups()):
        return "#{:02x}{:02x}{:02x}".format(*(int(v) for v in match.groups()))
    raise ValueError("文字颜色仅支持十六进制或 RGB 颜色")


def restricted_html(value: str) -> str:
    if len(value) > 20000:
        raise ValueError("商品说明最多 20000 个字符")
    parser = html5lib.HTMLParser(namespaceHTMLElements=False)
    fragment = parser.parseFragment(value)
    if parser.errors:
        raise ValueError("商品说明 HTML 格式无效，请在编辑器中修正后保存")
    for node in fragment.iter():
        if node is fragment:
            continue
        if not isinstance(node.tag, str) or node.tag not in ALLOWED_TAGS:
            raise ValueError("商品说明仅允许段落、标题、列表和文字格式；媒体请使用详情图集")
        for name, attribute in list(node.attrib.items()):
            if name == "color" and node.tag == "font":
                node.attrib[name] = _color(attribute)
            elif name == "style" and node.tag in {"span", "p", "font", *(f"h{i}" for i in range(1, 7))}:
                match = re.fullmatch(r"\s*color\s*:\s*([^;]+)\s*;?\s*", attribute, re.IGNORECASE)
                if match is None:
                    raise ValueError("商品说明只允许文字颜色样式")
                node.attrib[name] = f"color: {_color(match.group(1))};"
            else:
                raise ValueError("商品说明包含不支持的属性，请清除链接、媒体和额外格式")
    result = html5lib.serialize(
        fragment,
        tree="etree",
        quote_attr_values="always",
        omit_optional_tags=False,
        alphabetical_attributes=True,
        escape_lt_in_attrs=True,
    )
    if not isinstance(result, str) or len(result) > 20000:
        raise ValueError("规范化后的商品说明超出长度限制")
    return result


def legacy_text_to_html(value: str) -> str:
    return restricted_html("<p>" + escape(value).replace("\n", "<br>") + "</p>")

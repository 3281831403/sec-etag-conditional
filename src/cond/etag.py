"""条件请求判定的桩实现。

实体标签统一表示为字典：weak 为弱前缀标记，opaque 为引号内不透明串，
star 为字面量星号标记。完整契约见 README。修复时逐个实现下面的函数，
函数名、参数与返回结构保持不变。
"""

import math
from email.utils import parsedate_to_datetime


def _parse_http_date(value) -> float | None:
    """把 HTTP 日期解析成 Unix 秒；无法解析时返回 None。"""
    if not isinstance(value, str):
        return None
    try:
        return parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def parse_etag(text: str) -> dict:
    """解析单个实体标签，返回 weak、opaque、star 三个键。"""
    if not isinstance(text, str) or text == "":
        raise ValueError("实体标签不能为空")

    # 缺陷 4 修复：单独的星号是通配项，opaque 记为 "*"，star 为真。
    if text == "*":
        return {"weak": False, "opaque": "*", "star": True}

    # 缺陷 1 修复：弱前缀只认大写 W 加斜杠；小写 w/ 等写法落到引号校验并报错。
    weak = text.startswith("W/")
    body = text[2:] if weak else text

    # 缺陷 5 修复：去掉可选前缀后必须由一对双引号完整包住。
    if len(body) < 2 or body[0] != '"' or body[-1] != '"':
        raise ValueError(f"非法实体标签: {text!r}")
    opaque = body[1:-1]
    # 双引号只能出现在两端，引号内再次出现双引号同样非法。
    if '"' in opaque:
        raise ValueError(f"非法实体标签: {text!r}")

    return {"weak": weak, "opaque": opaque, "star": False}


def parse_list(text: str) -> list:
    """按逗号解析标签列表，逐项去空白，空文本返回空列表。"""
    # 缺陷 3 修复：必须拆成多个标签逐项解析，不能拿整串去比较。
    if text is None or text.strip() == "":
        return []
    items = []
    for raw in text.split(","):
        item = raw.strip()
        # 缺陷 5 延伸：连续逗号或首尾逗号会产生空项，属于非法输入。
        if item == "":
            raise ValueError("标签列表中存在空项")
        items.append(parse_etag(item))
    return items


def weak_compare(a: dict, b: dict) -> bool:
    """弱比较：忽略弱前缀，只比较不透明串。"""
    return a["opaque"] == b["opaque"]


def strong_compare(a: dict, b: dict) -> bool:
    """强比较：任一方为弱标签或星号即不相等。"""
    # 缺陷 2 修复：强比较不能直接复用弱比较，任一方带弱标记即不相等。
    if a["weak"] or b["weak"]:
        return False
    if a["star"] or b["star"]:
        return False
    return a["opaque"] == b["opaque"]


def match_none(request_list: list, etag: dict | None) -> bool:
    """条件命中判定：星号匹配存在的资源，标签走弱比较。"""
    # 缺陷 8 修复：etag 为 None 表示资源不存在，此时一律不命中，星号也不例外。
    if etag is None:
        return False
    # 缺陷 4 修复：星号是通配项，命中已存在的资源。
    if not request_list:
        return False
    for candidate in request_list:
        if candidate["star"]:
            return True
        if weak_compare(candidate, etag):
            return True
    return False


def match_tag(request_list: list, etag: dict | None) -> bool:
    """标签条件判定：星号匹配存在的资源，标签走强比较。"""
    # 与 match_none 相同：资源不存在时一律不命中。
    if etag is None:
        return False
    if not request_list:
        return False
    for candidate in request_list:
        if candidate["star"]:
            return True
        if strong_compare(candidate, etag):
            return True
    return False


def decide(headers: dict, etag: dict | None, last_modified, now) -> dict:
    """组合判定，返回 {"status": 304} 或 {"status": 200}，标签条件优先。"""
    # 头部字段名大小写不敏感。
    normalized = {str(key).lower(): value for key, value in headers.items()}

    # 缺陷 7 修复：if-none-match 存在时标签条件优先；不命中直接 200，
    # 不再回落评估 if-modified-since。
    inm = normalized.get("if-none-match")
    if inm is not None:
        candidates = parse_list(inm)
        if match_none(candidates, etag):
            # 缺陷 9 修复：条件命中返回 304 Not Modified，而非 200。
            return {"status": 304}
        return {"status": 200}

    ims = normalized.get("if-modified-since")
    if ims is not None:
        date_seconds = _parse_http_date(ims)
        # 缺陷 6 修复：两侧都归一（向下取整）到秒再比较，
        # 不能精确到毫秒，否则 STAMP+0.75 这类秒内偏移会造成永远不等。
        if date_seconds is not None and last_modified is not None:
            if math.floor(last_modified) <= math.floor(date_seconds):
                return {"status": 304}
        return {"status": 200}

    return {"status": 200}


def cond_batch(requests: list, policy: dict) -> dict:
    """批量判定，返回 id 到 decide 结果的字典，各请求相互独立。"""
    # 缺陷 10 修复：每个请求都用各自的 headers/etag/last_modified 重新判定，
    # 不缓存、不复用上一个请求解析出的标签或命中结果。
    policy = policy or {}
    now = policy.get("now", 0)
    results = {}
    for request in requests:
        results[request["id"]] = decide(
            request["headers"],
            request["etag"],
            request["last_modified"],
            now,
        )
    return results
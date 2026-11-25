"""条件请求判定的验收测试。

15 条测试与 README 的契约一一对应。基线状态下全部以 NotImplementedError 失败。
"""

import pytest

from cond.etag import (
    cond_batch,
    decide,
    match_none,
    match_tag,
    parse_etag,
    parse_list,
    strong_compare,
    weak_compare,
)

HTTP_DATE = "Wed, 21 Oct 2015 07:28:00 GMT"
STAMP = 1445412480  # HTTP_DATE 对应的秒级 Unix 时间戳


def test_defect_01_weak_prefix_recognized():
    weak = parse_etag('W/"v1"')
    assert weak["weak"] is True
    assert weak["opaque"] == "v1"
    assert weak["star"] is False
    assert parse_etag('"v1"')["weak"] is False


def test_defect_02_strong_compare_rejects_weak_tags():
    weak = parse_etag('W/"v1"')
    strong = parse_etag('"v1"')
    assert strong_compare(weak, strong) is False
    assert strong_compare(strong, weak) is False
    assert strong_compare(weak, weak) is False


def test_defect_03_list_is_split_into_items():
    parsed = parse_list('"a", W/"b" , "c"')
    assert [tag["opaque"] for tag in parsed] == ["a", "b", "c"]
    assert parsed[1]["weak"] is True
    assert parse_list("") == []
    assert parse_list("   ") == []


def test_defect_04_star_is_a_wildcard():
    star = parse_etag("*")
    assert star["star"] is True
    assert parse_list("*")[0]["star"] is True
    assert match_none(parse_list("*"), parse_etag('"v1"')) is True


def test_defect_05_missing_quotes_are_rejected():
    with pytest.raises(ValueError):
        parse_etag("v1")
    with pytest.raises(ValueError):
        parse_etag('"v1')
    with pytest.raises(ValueError):
        parse_etag("W/v1")


def test_defect_06_date_condition_uses_second_precision():
    result = decide(
        {"if-modified-since": HTTP_DATE},
        parse_etag('"v1"'),
        STAMP + 0.75,
        STAMP,
    )
    assert result["status"] == 304


def test_defect_07_tag_condition_takes_precedence():
    headers = {
        "if-none-match": '"other"',
        "if-modified-since": HTTP_DATE,
    }
    result = decide(headers, parse_etag('"v1"'), STAMP, STAMP)
    assert result["status"] == 200


def test_defect_08_star_does_not_match_missing_resource():
    assert match_none(parse_list("*"), None) is False
    result = decide({"if-none-match": "*"}, None, None, STAMP)
    assert result["status"] == 200


def test_defect_09_hit_returns_not_modified():
    result = decide({"if-none-match": '"v1"'}, parse_etag('"v1"'), None, STAMP)
    assert result["status"] == 304


def test_defect_10_batch_requests_do_not_share_state():
    requests = [
        {
            "id": "first",
            "headers": {"if-none-match": '"v1"'},
            "etag": parse_etag('"v1"'),
            "last_modified": None,
        },
        {
            "id": "second",
            "headers": {"if-none-match": '"v1"'},
            "etag": parse_etag('"v2"'),
            "last_modified": None,
        },
    ]
    result = cond_batch(requests, {})
    assert result["first"]["status"] == 304
    assert result["second"]["status"] == 200


def test_strong_tags_match_strongly():
    left = parse_etag('"v1"')
    right = parse_etag('"v1"')
    assert strong_compare(left, right) is True
    assert strong_compare(parse_etag('"v1"'), parse_etag('"v2"')) is False


def test_weak_tags_weak_match_but_do_not_strong_match():
    left = parse_etag('W/"v1"')
    right = parse_etag('W/"v1"')
    assert weak_compare(left, right) is True
    assert weak_compare(left, parse_etag('"v1"')) is True
    assert strong_compare(left, right) is False


def test_list_matches_any_item():
    candidates = parse_list('"a", "b", "c"')
    assert match_none(candidates, parse_etag('"b"')) is True
    assert match_none(candidates, parse_etag('"z"')) is False


def test_star_matches_existing_resource():
    assert match_none(parse_list("*"), parse_etag('"v1"')) is True
    assert match_tag(parse_list("*"), parse_etag('"v1"')) is True


def test_batch_equals_individual_decisions():
    requests = [
        {
            "id": "hit",
            "headers": {"if-none-match": '"v1"'},
            "etag": parse_etag('"v1"'),
            "last_modified": None,
        },
        {
            "id": "miss",
            "headers": {"if-none-match": '"v2"'},
            "etag": parse_etag('"v1"'),
            "last_modified": None,
        },
        {
            "id": "dated",
            "headers": {"if-modified-since": HTTP_DATE},
            "etag": parse_etag('"v1"'),
            "last_modified": STAMP,
        },
    ]
    batch = cond_batch(requests, {})
    for item in requests:
        single = decide(item["headers"], item["etag"], item["last_modified"], STAMP)
        assert batch[item["id"]] == single
缓存校验加了实体标签之后，弱标签被当成强标签比较，命中判断全反了：一是弱前缀没有被识别，大写 W 加斜杠的标签被当成普通强标签；二是强比较直接复用了弱比较，弱标签也能通过强匹配；三是列表解析按整串比较，多标签列表只比对第一个标签；四是星号通配没有被识别，星号被当成普通标签参与比较；五是缺失双引号的标签被接受，非法输入没有报错；六是日期条件比较精确到毫秒，秒级时间戳永远不相等；七是标签条件与日期条件的优先级颠倒，先看日期再看标签；八是资源不存在时星号条件被判为命中；九是命中时的状态码与契约相反，本应返回未修改却返回成功；十是批量判定复用条件结果，第二个请求沿用第一个请求的标签。cond/etag.py 是核心，tests/test_etag.py 15个红。要修的是：按上面的顺序把 10 个缺陷逐个修掉。

## 运行方式

在仓库根目录执行：

    python -m pytest tests -q

当前基线为 15 failed，15 条失败全部由 NotImplementedError 引起，收集阶段没有错误、导入没有错误、也没有断言失败。修复完成后应为 15 passed。

## 字段表

| 字段 | 内容 |
| --- | --- |
| 题目类型 | 安全 |
| 细分方向 | 漏洞检测与攻防 |
| 任务类型 | Bugfix |
| 语言与测试 | Python 3, pytest |
| 外部依赖 | 无外部依赖 |

## 目录结构

    sec-etag-conditional/
      README.md
      pyproject.toml
      tests/conftest.py
      tests/test_etag.py
      src/cond/__init__.py
      src/cond/etag.py

## src 布局说明

源码采用 src 布局，包名为 cond，唯一实现文件是 src/cond/etag.py。tests/conftest.py 在测试收集阶段把仓库根目录下的 src 加入 sys.path，pyproject.toml 中的 pytest 配置也把 pythonpath 指向 src，因此从仓库根直接运行 pytest 就能导入 cond，不需要先安装或先打包。

## tests 不可修改

tests/test_etag.py 与 tests/conftest.py 是验收标准，禁止修改、删除、跳过或拆分其中的用例，不要改动断言、测试名与用例数量。需要修改的文件只有 src/cond/etag.py。

## 接口契约

实体标签统一用字典表示，键为 weak、opaque、star：weak 是布尔值，表示带弱前缀；opaque 是引号内的不透明串，原样保存，不做反转义；star 是布尔值，表示字面量星号通配项。星号项的 weak 为假、opaque 为星号字符、star 为真。

parse_etag(text) 解析单个标签，返回上述字典。弱前缀只接受大写 W 加斜杠；去掉前缀后必须由一对双引号完整包住，引号外出现多余字符、缺少任意一侧引号、空文本都抛 ValueError。引号内允许空串。

parse_list(text) 解析标签列表，按逗号切分并逐项去首尾空白，每项交给 parse_etag。空文本或纯空白返回空列表；出现空项时抛 ValueError，例如连续逗号或末尾逗号。

weak_compare(a, b) 做弱比较，忽略 weak 标记，只比较 opaque，相等返回 True。strong_compare(a, b) 做强比较，任意一方 weak 为真即返回 False，任意一方 star 为真也返回 False，只有两方都是强标签且 opaque 相等才返回 True。

match_none(request_list, etag) 判断条件是否命中。etag 为 None 表示资源不存在，此时一律返回 False，星号也不例外；request_list 为空返回 False；任一项 star 为真返回 True；否则任一项与 etag 弱比较相等即返回 True。

match_tag(request_list, etag) 的判定层次与 match_none 相同，但标签之间改用强比较。

decide(headers, etag, last_modified, now) 返回字典，状态码放在 status 键，取值仅为 304 或 200。headers 的键按大小写不敏感匹配。if-none-match 存在时以标签条件为准，命中返回 304，不命中直接返回 200，此时忽略 if-modified-since。if-none-match 缺失而 if-modified-since 存在时，把 last_modified 与头部日期都归一到秒再比较，last_modified 不晚于头部日期返回 304，否则返回 200；last_modified 为 None 或日期无法解析时返回 200。两个条件头都缺失返回 200。now 是当前 Unix 时间戳，作为接口参数保留，不参与上述比较。last_modified 与 now 都是 Unix 秒，可以是整数或浮点数。

cond_batch(requests, policy) 批量判定。requests 是列表，每项包含 id、headers、etag、last_modified 四个键；policy 是字典，可含 now，缺省为 0。返回以 id 为键、decide 结果为值的字典，空列表返回空字典。每个请求完全独立，不得复用上一个请求的标签、解析结果或条件结果。

## 边角约定

1. 弱前缀只认大写 W 加斜杠，小写 w 加斜杠属于非法输入。
2. 弱标签的 weak 为真，强标签的 weak 为假。
3. 强比较中任意一方为弱即不相等，两个弱标签之间也不强相等。
4. 弱比较忽略 weak 标记，只比较 opaque。
5. 列表按逗号切分，逐项去空白，空文本与纯空白得到空列表。
6. 列表中出现空项属于非法输入，抛 ValueError。
7. 星号是独立的通配项，star 为真，不按普通不透明串处理。
8. 星号只匹配存在的资源，资源不存在时星号不命中。
9. 标签必须由成对双引号包住，双引号只出现在两端；缺失引号、引号外有多余字符或引号内再次出现双引号都抛 ValueError。
10. 日期条件按秒比较，last_modified 向下取整到秒。
11. if-none-match 的优先级高于 if-modified-since。
12. if-none-match 存在但不命中时直接返回 200，不再回落到日期条件。
13. 条件命中返回 304，未命中返回 200。
14. 头部字段名大小写不敏感，缺失头部视为无条件请求。
15. 空请求列表不命中，空批量返回空字典。
16. 批量判定逐请求独立，结果与逐个调用 decide 完全一致。

## 15 个测试

缺陷回归 10 条，一一对应题面的 10 个缺陷：

1. test_defect_01_weak_prefix_recognized
2. test_defect_02_strong_compare_rejects_weak_tags
3. test_defect_03_list_is_split_into_items
4. test_defect_04_star_is_a_wildcard
5. test_defect_05_missing_quotes_are_rejected
6. test_defect_06_date_condition_uses_second_precision
7. test_defect_07_tag_condition_takes_precedence
8. test_defect_08_star_does_not_match_missing_resource
9. test_defect_09_hit_returns_not_modified
10. test_defect_10_batch_requests_do_not_share_state

正向契约 5 条：

11. test_strong_tags_match_strongly
12. test_weak_tags_weak_match_but_do_not_strong_match
13. test_list_matches_any_item
14. test_star_matches_existing_resource
15. test_batch_equals_individual_decisions

## 字段表

| 字段 | 取值 |
| --- | --- |
| 所属领域 | 安全 |
| 子方向 | 漏洞检测与攻防 |
| 任务类型 | Bugfix |
| 语言/框架 | Python 3, pytest |
| 环境可复现等级 | 无外部依赖 |


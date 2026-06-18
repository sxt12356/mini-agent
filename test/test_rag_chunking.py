from mini_agent.rag.chunking import build_chunks_for_document, split_into_sections


def test_split_into_sections_with_markdown_headings():
    text = """
# 退款政策

## 退款条件

未发货订单不走退款流程，用户应优先取消订单。

## 审核与到账

退款审核通常需要 1-3 个工作日。
"""

    sections = split_into_sections(text)

    assert len(sections) == 2
    assert sections[0].section_title == "退款政策 / 退款条件"
    assert "未发货订单" in sections[0].content
    assert sections[1].section_title == "退款政策 / 审核与到账"
    assert "退款审核" in sections[1].content


def test_build_chunks_keep_metadata():
    text = """
# 会员政策

## 黑卡会员

黑卡会员享受免费退货服务。
"""

    chunks = build_chunks_for_document(
        source="membership_policy.txt",
        text=text,
        max_chars=300,
        overlap_paragraphs=1,
    )

    assert len(chunks) == 1

    chunk = chunks[0]

    assert chunk.source == "membership_policy.txt"
    assert chunk.section == "会员政策 / 黑卡会员"
    assert chunk.heading_path == ["会员政策", "黑卡会员"]
    assert "黑卡会员" in chunk.text
    assert "免费退货" in chunk.text


def test_long_section_is_split_into_multiple_chunks():
    text = """
# 测试文档

## 长章节

第一段内容。
第二段内容。
第三段内容。
第四段内容。
第五段内容。
"""

    chunks = build_chunks_for_document(
        source="test.txt",
        text=text,
        max_chars=30,
        overlap_paragraphs=1,
    )

    assert len(chunks) >= 2

    for chunk in chunks:
        assert chunk.source == "test.txt"
        assert chunk.section == "测试文档 / 长章节"

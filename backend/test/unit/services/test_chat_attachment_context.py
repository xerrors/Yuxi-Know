from langchain.messages import HumanMessage

from yuxi.modules.agents.services.execution import _with_attachment_context


def test_attachment_context_is_added_only_to_model_message():
    original = HumanMessage(content="请总结附件")

    model_message = _with_attachment_context(
        original,
        [
            {
                "file_name": "report.pdf",
                "path": "/home/user/workspace/projects/project-1/uploads/report.pdf",
            }
        ],
    )

    assert original.content == "请总结附件"
    assert model_message.content.startswith("请总结附件\n\n<attachment_context>")
    assert "report.pdf" in model_message.content
    assert model_message.type == "human"


def test_attachment_context_preserves_multimodal_content_blocks():
    image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}
    original = HumanMessage(content=[{"type": "text", "text": "比较图片"}, image])

    model_message = _with_attachment_context(
        original,
        [{"file_name": "notes.md", "path": "/home/user/workspace/projects/project-1/uploads/notes.md"}],
    )

    assert model_message.content[:2] == original.content
    assert model_message.content[-1]["type"] == "text"
    assert "<attachment_context>" in model_message.content[-1]["text"]


def test_attachment_context_ignores_records_without_paths():
    original = HumanMessage(content="继续")

    assert _with_attachment_context(original, [{"file_name": "missing"}]) is original

"""问题和选项规范化工具"""

import uuid
from typing import Any


def normalize_options(raw_options: Any) -> list[dict[str, str]]:
    """规范化选项列表"""
    if not isinstance(raw_options, list):
        return []

    options: list[dict[str, str]] = []
    for item in raw_options:
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("value") or "").strip()
            value = str(item.get("value") or item.get("label") or "").strip()
        else:
            label = str(item).strip()
            value = label
        if label and value:
            options.append({"label": label, "value": value})
    return options


def normalize_questions(raw_questions: Any, default_question_id_prefix: str = "q") -> list[dict[str, Any]]:
    """规范化问题列表"""
    if not isinstance(raw_questions, list):
        return []

    questions: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_questions):
        if not isinstance(item, dict):
            continue

        question = str(item.get("question") or "").strip()
        if not question:
            continue

        question_id = str(item.get("question_id") or f"{default_question_id_prefix}-{idx + 1}").strip()
        if not question_id:
            question_id = str(uuid.uuid4())

        normalized_question: dict[str, Any] = {
            "question_id": question_id,
            "question": question,
            "options": normalize_options(item.get("options")),
            "multi_select": bool(item.get("multi_select", False)),
            "allow_other": bool(item.get("allow_other", True)),
        }

        operation = item.get("operation")
        if isinstance(operation, str) and operation.strip():
            normalized_question["operation"] = operation.strip()

        questions.append(normalized_question)

    return questions


def normalize_legacy_question(raw_question: Any) -> dict[str, Any] | None:
    """规范化单个问题（兼容旧格式）"""
    if not raw_question:
        return None

    question = str(raw_question.get("question") or "").strip()
    if not question:
        return None

    question_id = str(raw_question.get("question_id") or "").strip()
    if not question_id:
        question_id = str(uuid.uuid4())

    return {
        "question_id": question_id,
        "question": question,
        "options": normalize_options(raw_question.get("options")),
        "multi_select": bool(raw_question.get("multi_select", False)),
        "allow_other": bool(raw_question.get("allow_other", True)),
    }

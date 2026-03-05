from __future__ import annotations

import csv
import re
from typing import Any


def _rm_prefix(text: str) -> str:
    return re.sub(
        r"^(问题|答案|回答|user|assistant|Q|A|Question|Answer|问|答)[\t:： ]+",
        "",
        (text or "").strip(),
        flags=re.IGNORECASE,
    )


def _to_qa_chunk(question: str, answer: str, eng: bool = False) -> str:
    qprefix = "Question: " if eng else "问题："
    aprefix = "Answer: " if eng else "回答："
    return "\t".join([qprefix + _rm_prefix(question), aprefix + _rm_prefix(answer)])


def _guess_delimiter(lines: list[str]) -> str:
    comma = 0
    tab = 0
    for line in lines:
        if len(line.split(",")) == 2:
            comma += 1
        if len(line.split("\t")) == 2:
            tab += 1
    return "\t" if tab >= comma else ","


def _extract_pairs_with_delimiter(lines: list[str], delimiter: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    question = ""
    answer = ""

    for line in lines:
        arr = line.split(delimiter)
        if len(arr) != 2:
            if question:
                answer += "\n" + line
            continue

        if question and answer:
            pairs.append((question, answer))
        question, answer = arr

    if question:
        pairs.append((question, answer))

    return [(q.strip(), a.strip()) for q, a in pairs if q.strip()]


def _extract_pairs_from_csv(lines: list[str], delimiter: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    question = ""
    answer = ""

    reader = csv.reader(lines, delimiter=delimiter)
    for row, raw_line in zip(reader, lines, strict=False):
        if len(row) != 2:
            if question:
                answer += "\n" + raw_line
            continue

        if question and answer:
            pairs.append((question, answer))
        question, answer = row

    if question:
        pairs.append((question, answer))

    return [(q.strip(), a.strip()) for q, a in pairs if q.strip()]


def _parse_markdown_table_row(line: str) -> list[str] | None:
    if "|" not in line:
        return None

    text = line.strip()
    if not text:
        return None

    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]

    cells = [cell.strip() for cell in text.split("|")]
    if not cells:
        return None

    if all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cells if c):
        return None

    return cells


def _extract_pairs_from_markdown_tables(markdown_content: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []

    for line in (markdown_content or "").splitlines():
        cells = _parse_markdown_table_row(line)
        if not cells or len(cells) < 2:
            continue

        question = cells[0]
        answer = cells[1]
        if question and answer:
            pairs.append((question, answer))

    return pairs


def _md_question_level(line: str) -> tuple[int, str]:
    match = re.match(r"^#*", line)
    if not match:
        return 0, line
    return len(match.group(0)), line.lstrip("#").lstrip()


def _extract_pairs_from_markdown_headings(markdown_content: str) -> list[tuple[str, str]]:
    lines = (markdown_content or "").splitlines()
    if not lines:
        return []

    pairs: list[tuple[str, str]] = []
    last_answer = ""
    question_stack: list[str] = []
    level_stack: list[int] = []
    code_block = False

    for line in lines:
        if line.strip().startswith("```"):
            code_block = not code_block

        question_level = 0
        question = ""
        if not code_block:
            question_level, question = _md_question_level(line)

        if not question_level or question_level > 6:
            last_answer = f"{last_answer}\n{line}"
            continue

        if last_answer.strip():
            sum_question = "\n".join(question_stack)
            if sum_question:
                pairs.append((sum_question, last_answer.strip()))
            last_answer = ""

        while question_stack and question_level <= level_stack[-1]:
            question_stack.pop()
            level_stack.pop()

        question_stack.append(question)
        level_stack.append(question_level)

    if last_answer.strip():
        sum_question = "\n".join(question_stack)
        if sum_question:
            pairs.append((sum_question, last_answer.strip()))

    return pairs


def _extract_pairs_by_prefix(lines: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    question = ""
    answer_lines: list[str] = []

    for line in lines:
        if re.match(r"^(Q|Question|问|问题)\s*[:：]", line, flags=re.IGNORECASE):
            if question:
                pairs.append((question, "\n".join(answer_lines)))
            question = re.sub(r"^(Q|Question|问|问题)\s*[:：]", "", line, flags=re.IGNORECASE).strip()
            answer_lines = []
            continue

        if re.match(r"^(A|Answer|答|回答)\s*[:：]", line, flags=re.IGNORECASE):
            answer_lines.append(re.sub(r"^(A|Answer|答|回答)\s*[:：]", "", line, flags=re.IGNORECASE).strip())
            continue

        if question:
            answer_lines.append(line)

    if question:
        pairs.append((question, "\n".join(answer_lines)))

    return [(q.strip(), a.strip()) for q, a in pairs if q.strip() and a.strip()]


def _dedupe_pairs(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    res: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for question, answer in pairs:
        q = question.strip()
        a = answer.strip()
        if not q or not a:
            continue
        key = (q, a)
        if key in seen:
            continue
        seen.add(key)
        res.append((q, a))

    return res


def chunk_markdown(filename: str, markdown_content: str, parser_config: dict[str, Any] | None = None) -> list[str]:
    parser_config = parser_config or {}
    eng = str(parser_config.get("language", "Chinese")).lower() == "english"

    suffix = ""
    if filename and "." in filename:
        suffix = "." + filename.lower().split(".")[-1]

    lines = [line for line in (markdown_content or "").splitlines() if line.strip()]
    pairs: list[tuple[str, str]] = []

    if suffix in {".xlsx", ".xls"}:
        pairs.extend(_extract_pairs_from_markdown_tables(markdown_content))
        if not pairs:
            delimiter = _guess_delimiter(lines)
            pairs.extend(_extract_pairs_with_delimiter(lines, delimiter))
    elif suffix == ".csv":
        pairs.extend(_extract_pairs_from_markdown_tables(markdown_content))
        delimiter = "\t" if any("\t" in line for line in lines) else ","
        pairs.extend(_extract_pairs_from_csv(lines, delimiter))
    elif suffix == ".txt":
        delimiter = _guess_delimiter(lines)
        pairs.extend(_extract_pairs_with_delimiter(lines, delimiter))
    elif suffix in {".md", ".markdown", ".mdx"}:
        pairs.extend(_extract_pairs_from_markdown_headings(markdown_content))
        pairs.extend(_extract_pairs_from_markdown_tables(markdown_content))
    elif suffix == ".docx":
        pairs.extend(_extract_pairs_from_markdown_headings(markdown_content))
        pairs.extend(_extract_pairs_from_markdown_tables(markdown_content))
    else:
        pairs.extend(_extract_pairs_from_markdown_headings(markdown_content))
        pairs.extend(_extract_pairs_from_markdown_tables(markdown_content))
        pairs.extend(_extract_pairs_by_prefix(lines))
        if not pairs:
            delimiter = _guess_delimiter(lines)
            pairs.extend(_extract_pairs_with_delimiter(lines, delimiter))

    pairs = _dedupe_pairs(pairs)

    if not pairs and lines:
        # 最后兜底：把内容按 2 行一组构成问答
        for i in range(0, len(lines), 2):
            q = lines[i]
            a = lines[i + 1] if i + 1 < len(lines) else ""
            if q.strip() and a.strip():
                pairs.append((q, a))

    return [_to_qa_chunk(q, a, eng=eng) for q, a in pairs]

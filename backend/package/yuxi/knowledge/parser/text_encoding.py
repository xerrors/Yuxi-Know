"""用户上传文本的编码识别与解码。"""

from __future__ import annotations

import codecs

import chardet

from yuxi.utils import logger

# BOM 必须在探测之前处理：UTF-16 的 ASCII 区间含大量空字节，探测器可能给出单字节编码。
_BOM_ENCODINGS = (
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)


def decode_user_text(raw: bytes, source: str) -> str:
    """把用户上传的文本字节解码为字符串，兼容 UTF-8、带 BOM 与常见中文编码。"""
    for bom, encoding in _BOM_ENCODINGS:
        if raw.startswith(bom):
            return _decode(raw, encoding, source)

    # 含 NUL 的输入不做 UTF-8 快路径（NUL 是合法 UTF-8 字节，无 BOM 的 UTF-16 会静默产出
    # 字符间夹杂空字节的垃圾），交给探测器；UTF-32 等含 NUL 的编码不在本函数承诺范围。
    if b"\x00" not in raw[:4096]:
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            pass

    result = chardet.detect(raw)
    detected = str(result.get("encoding") or "")
    confidence = result.get("confidence") or 0.0
    if confidence < 0.5:
        # 低置信探测仍会尝试严格解码，但必须留下可定位痕迹：误判为兼容单字节编码时
        # 严格解码可能"成功"并静默产出乱码。
        logger.warning(f"文本编码低置信识别: {source} (detected={detected}, confidence={confidence:.2f})")
    return _decode(raw, detected, source)


def _decode(raw: bytes, encoding: str, source: str) -> str:
    """严格解码识别到的编码；编码不可用或存在坏字节时替换兜底并留下告警。"""
    codec = encoding.lower() or "utf-8"
    try:
        codecs.lookup(codec)
    except LookupError:
        logger.warning(f"文本编码识别失败，按 UTF-8 解码: {source} (detected={encoding})")
        codec = "utf-8"

    try:
        return raw.decode(codec)
    except UnicodeDecodeError as exc:
        logger.warning(f"文本按 {codec} 解码不完整，使用替换兜底: {source} ({exc.reason}, offset {exc.start})")
        return raw.decode(codec, errors="replace")

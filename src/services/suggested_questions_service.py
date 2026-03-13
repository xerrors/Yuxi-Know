"""猜你想问服务 - 基于对话历史生成建议问题"""

import re
from typing import Any

from sqlalchemy import select

from src import config as conf
from src.models.chat import select_model
from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import Conversation, SuggestedQuestion
from src.utils.logging_config import logger

# Redis key 前缀
REDIS_KEY_PREFIX = "suggested_questions:generating:"
REDIS_KEY_TTL = 300  # 5分钟过期


async def _get_redis():
    """获取 Redis 客户端"""
    from src.services.run_queue_service import get_redis_client

    return await get_redis_client()


async def _try_set_generating(thread_id: str) -> bool:
    """尝试标记正在生成（原子操作），返回是否成功"""
    try:
        redis = await _get_redis()
        key = f"{REDIS_KEY_PREFIX}{thread_id}"
        # SETNX: 只有 key 不存在时才设置，返回 1 表示成功，0 表示失败
        result = await redis.set(key, "1", ex=REDIS_KEY_TTL, nx=True)
        return result is True or result == 1
    except Exception as e:
        logger.warning(f"Redis try_set_generating failed: {e}")
        return True  # Redis 失败时允许继续，避免阻塞


async def _clear_generating(thread_id: str) -> None:
    """清除生成标记"""
    try:
        redis = await _get_redis()
        key = f"{REDIS_KEY_PREFIX}{thread_id}"
        await redis.delete(key)
    except Exception as e:
        logger.warning(f"Redis clear_generating failed: {e}")


async def is_generating(thread_id: str) -> bool:
    """检查指定会话是否正在生成建议问题"""
    try:
        redis = await _get_redis()
        key = f"{REDIS_KEY_PREFIX}{thread_id}"
        return await redis.exists(key) > 0
    except Exception as e:
        logger.warning(f"Redis is_generating check failed: {e}")
        return False


def extract_questions_by_markers(text: str, max_count: int = 3) -> list[str]:
    """提取带数字编号的问题"""
    suggestions = []

    patterns = [
        # 模式1：问题1：内容
        r"问题\s*(\d+)\s*[:：]\s*(.+?)(?=\s*(?:问题\s*\d+\s*[:：]|$))",
        # 模式2：1. 内容
        r"(?<!\d)(\d+)\s*[\.、:：]\s*(.+?)(?=\s*(?:\d+\s*[\.、:：]|$))",
        # 模式3：一、内容
        r"([一二三四五六七八九十百千万]+)[、:：]\s*(.+?)(?=\s*(?:[一二三四五六七八九十百千万]+[、:：]|$))",
    ]

    for pattern in patterns:
        if len(suggestions) >= max_count:
            break

        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            if len(suggestions) >= max_count:
                break

            if isinstance(match, tuple):
                content = match[1].strip() if len(match) > 1 else match[0].strip()
            else:
                content = match.strip()

            if content and content not in suggestions:
                suggestions.append(content)

    return suggestions[:max_count]


async def generate_suggested_questions_by_thread_id(thread_id: str) -> list[str]:
    """
    基于对话历史生成建议问题（使用 fast_model）

    Args:
        thread_id: 会话ID

    Returns:
        建议问题列表
    """
    # 原子操作：尝试标记正在生成，失败说明已有任务在执行
    if not await _try_set_generating(thread_id):
        logger.debug(f"已有生成任务在执行: {thread_id}")
        return []
    try:
        async with pg_manager.get_async_session_context() as db:
            # 获取对话
            result = await db.execute(select(Conversation).where(Conversation.thread_id == thread_id))
            conversation = result.scalar_one_or_none()
            if not conversation:
                logger.warning(f"Conversation not found for thread_id: {thread_id}")
                return []

            # 获取对话历史消息（多取一些，因为可能有多个 assistant 消息如 tool_calls）
            from src.storage.postgres.models_business import Message
            msg_result = await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.desc())
                .limit(20)
            )
            messages = list(reversed(msg_result.scalars().all()))  # 按时间正序

            if not messages:
                return []

            # 构建对话文本：一个 user 消息 + 该 user 后的最后一个 assistant 消息 = 一轮对话
            # 从前往后遍历，遇到 user 记录问题，遇到 assistant 时更新当前问题的答案
            # 这样一个 user 后面的多个 assistant 消息，只有最后一个会被保留
            recent_dialogues: list[dict] = []
            for msg in messages:
                if msg.role == "user":
                    # 新的一轮对话开始
                    recent_dialogues.append({"question": msg.content, "answer": ""})
                elif msg.role == "assistant" and recent_dialogues:
                    # 更新当前对话的答案（多个 assistant 时只保留最后一个）
                    recent_dialogues[-1]["answer"] = msg.content

            # 过滤掉没有回答的（可能最后一条是 user 还没回复）
            dialogues = [d for d in recent_dialogues if d["answer"]]
            if not dialogues:
                return []

            # 构建对话文本
            recent_dialogues = dialogues[-3:]  # 最近3轮
            dialogue_text = ""
            for i, d in enumerate(recent_dialogues, 1):
                dialogue_text += f"\n第{i}轮对话：\n问题：{d['question']}\n回答：{d['answer'][:500]}\n"

            # 获取历史建议问题用于去重
            existing_sq = await db.execute(
                select(SuggestedQuestion)
                .where(SuggestedQuestion.conversation_id == conversation.id)
            )
            existing = existing_sq.scalar_one_or_none()
            recent_questions = existing.questions if existing else []

            # 构建提示词
            prompt = f"""基于以下的对话历史（共{len(recent_dialogues)}轮对话，按照时间顺序排列，越往后的对话越新，请重点关注最新的对话），生成3个用户接下来可能问的问题：{dialogue_text}

    【重要说明】：
    1. 请特别关注较新的对话，它们代表了最近的讨论方向
    2. 生成的问题应该基于整个对话历史，但优先考虑最近对话的延续
    3. 问题应该自然、相关，能推动对话深入"""

            # 只有在 recent_questions 存在且有足够元素时才添加第4点
            if recent_questions and len(recent_questions) >= 3:
                prompt += f"""
    4. 区别于下列三个问题:{recent_questions[0]}、{recent_questions[1]}、{recent_questions[2]}"""

            # 添加公共部分
            prompt += """
    请直接返回3个简短【50字以内】、相关的问题，并严格按照以下格式输出，每个问题一行，不要出现任何的多余解释或词汇：
        问题1：第一个问题
        问题2：第二个问题
        问题3：第三个问题
    """

            # 使用 fast_model
            model = select_model(model_spec=conf.fast_model)
            response = await model.call([{"role": "user", "content": prompt}], stream=False)

            content = response.content if hasattr(response, "content") else str(response)
            suggestions = extract_questions_by_markers(content, 3)

            # 保存到数据库
            if suggestions:
                await _upsert_suggested_questions(db, conversation.id, suggestions)

            return suggestions

    except Exception as e:
        logger.error(f"生成建议问题失败: {e}")
        return []
    finally:
        # 无论成功失败，都移除标记
        await _clear_generating(thread_id)


async def _upsert_suggested_questions(db, conversation_id: int, questions: list[str]) -> None:
    """更新或插入建议问题"""
    result = await db.execute(
        select(SuggestedQuestion).where(SuggestedQuestion.conversation_id == conversation_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.questions = questions
    else:
        sq = SuggestedQuestion(conversation_id=conversation_id, questions=questions)
        db.add(sq)

    await db.commit()


async def get_suggested_questions_by_thread_id(thread_id: str) -> dict[str, Any]:
    """
    获取建议问题

    Returns:
        {
            "questions": list[str],  # 建议问题列表
            "is_generating": bool    # 是否正在生成中
        }
    """
    try:
        # 先检查是否正在生成
        generating = await is_generating(thread_id)

        async with pg_manager.get_async_session_context() as db:
            result = await db.execute(
                select(SuggestedQuestion)
                .join(Conversation)
                .where(Conversation.thread_id == thread_id)
                .order_by(SuggestedQuestion.updated_at.desc())
            )
            sq = result.scalar_one_or_none()
            questions = sq.questions if sq else []

            return {
                "questions": questions,
                "is_generating": generating
            }
    except Exception as e:
        logger.error(f"获取建议问题失败: {e}")
        return {"questions": [], "is_generating": False}


async def generate_suggested_questions_safe(thread_id: str) -> None:
    """安全的生成建议问题（异步执行，不抛出异常）"""
    try:
        await generate_suggested_questions_by_thread_id(thread_id)
    except Exception as e:
        logger.error(f"异步生成建议问题失败: {e}")
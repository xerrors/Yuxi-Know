"""LangGraph v3 ProtocolEvent 到 OpenAI Agents 公开事件的唯一适配入口。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.agents.repositories.public_items import PublicItemRepository
from yuxi.modules.agents.services.public_items import serialize_public_items
from yuxi.shared.hashing import hash_id


class OpenAIEventAdapter:
    """保留内容块关联；只发布当前 Run 明确归属的用户可见输出。"""

    def __init__(self, *, run_id: str, turn_id: str, thread_id: str, worker_id: str):
        """绑定业务执行身份，源 payload 不参与路由。"""
        self.run_id = run_id
        self.turn_id = turn_id
        self.thread_id = thread_id
        self.worker_id = worker_id
        self.models: dict[tuple, dict] = {}
        self.calls: dict[str, tuple[str, str, dict]] = {}

    async def consume(self, event: dict) -> list[dict]:
        """消费记录器返回的 messages/tools 事件，消息事实已提交、工具结果已规整。"""
        method = event.get("method")
        if method == "messages":
            message, metadata = event["params"]["data"]
            if (metadata or {}).get("thread_id", self.thread_id) != self.thread_id:
                return []
            return await self._message(event, message, metadata or {})
        if method == "tools":
            return await self._tool(event, event["params"]["data"])
        return []

    async def finish(self) -> list[dict]:
        """提交业务结果后，按相同公开 serializer 发布最终 item 边界。"""
        async with pg_manager.get_async_session_context() as db:
            from yuxi.modules.agents.repositories.runs import AgentRunRepository

            run = await AgentRunRepository(db).get_run(self.run_id)
            rows = await PublicItemRepository(db).list_items(thread_id=self.thread_id, uid=run.uid, app_id=run.app_id, turn_id=self.turn_id)
        events = []
        related_calls = {
            item["yuxi"]["call_item_id"]
            for message, owner, result_id in rows
            if message.run_id == self.run_id
            for item in serialize_public_items(message, owner, result_id)
            if item["type"] == "function_call_output"
        }
        for message, owner, result_id in rows:
            for item in serialize_public_items(message, owner, result_id):
                if message.run_id != self.run_id and item["id"] not in related_calls:
                    continue
                if item["type"] == "message" and item["role"] != "assistant":
                    continue
                events.append(
                    self._event(
                        "agent.session.turn.item.done",
                        f"settled:{item['id']}",
                        output_index=item["yuxi"]["output_index"],
                        item=item,
                    )
                )
        return events

    async def persist_incomplete(self, *, cancelled_partial: bool = False) -> None:
        """失败收敛前保存已展示的正文和推理，不承诺逐 token 落库。"""
        for model in self.models.values():
            if model["item"] is not None and model["item"]["status"] == "in_progress":
                item = model["item"]
                item["status"] = "incomplete"
                item["yuxi"]["reasoning"] = dict(model["reasoning"])
                if cancelled_partial:
                    async with pg_manager.get_async_session_context() as db:
                        model["item"] = await PublicItemRepository(db).save(
                            run_id=self.run_id,
                            worker_id=self.worker_id,
                            operation_id=model["operation_id"],
                            role="assistant",
                            key="message",
                            item=item,
                            cancelled_partial=True,
                        )
                else:
                    model["item"] = await self._save(model["operation_id"], "assistant", "message", item)

    def extension(self, name: str, identity: str, **fields) -> dict:
        """生成业务明确选取内容的扩展事件。"""
        return self._event(f"yuxi.session.{name}", identity, **fields)

    async def _message(self, event: dict, message: Any, metadata: dict) -> list[dict]:
        """将原生内容块转换为公开 message 和 function_call。"""
        if not isinstance(message, dict) or "event" not in message:
            return []
        key = (metadata.get("run_id") or metadata.get("langgraph_node"), tuple(event["params"].get("namespace") or []))
        kind = message["event"]
        events = []
        if kind == "message-start":
            self.models[key] = {
                "operation_id": str(message.get("id") or metadata.get("run_id")),
                "item": None,
                "blocks": {},
                "reasoning": {},
            }
            return []
        model = self.models.get(key)
        if model is None:
            raise ValueError("模型内容块缺少相同来源的 message-start")
        index = message.get("index", 0)
        block = message.get("content") or message.get("delta") or {}
        if kind == "content-block-start":
            # tool_call 的参数由上游 finish 一次给出，不制造参数增量。
            if block.get("type") == "text":
                events.extend(await self._ensure_message(model, event))
                content_index = len(model["blocks"])
                model["blocks"][index] = content_index
                model["item"]["content"].append({"type": "output_text", "text": ""})
                model["item"]["yuxi"]["content_blocks"] = dict(model["blocks"])
                events.append(
                    self._content_event("content_part.added", event, model, content_index, part={"type": "output_text", "text": ""})
                )
            return events
        if kind == "content-block-delta":
            if block.get("type") == "text-delta":
                events.extend(await self._ensure_text_block(model, event, index))
                content_index = model["blocks"][index]
                delta = block.get("text", "")
                model["item"]["content"][content_index]["text"] += delta
                events.append(self._content_event("output_text.delta", event, model, content_index, delta=delta))
            elif block.get("type") in {"reasoning-delta", "thinking-delta"}:
                events.extend(await self._ensure_message(model, event))
                delta = block.get("reasoning") or block.get("text") or block.get("thinking") or ""
                model["reasoning"][index] = model["reasoning"].get(index, "") + delta
                events.append(self._content_event("reasoning.delta", event, model, index, extension=True, delta=delta))
            return events
        if kind == "content-block-finish":
            block_type = block.get("type")
            if block_type == "text":
                events.extend(await self._ensure_text_block(model, event, index))
                content_index = model["blocks"][index]
                text = block.get("text", "")
                part = {"type": "output_text", "text": text}
                model["item"]["content"][content_index] = part
                model["item"]["yuxi"].setdefault("completed_content_indices", []).append(content_index)
                model["item"] = await self._save(model["operation_id"], "assistant", "message", model["item"])
                events.append(self._content_event("output_text.done", event, model, content_index, text=text))
                events.append(self._content_event("content_part.done", event, model, content_index, part=part))
            elif block_type in {"reasoning", "thinking"}:
                events.extend(await self._ensure_message(model, event))
                text = block.get("reasoning") or block.get("text") or block.get("thinking") or model["reasoning"].get(index, "")
                model["reasoning"][index] = text
                model["item"]["yuxi"].setdefault("completed_reasoning_indices", []).append(index)
                model["item"]["yuxi"]["reasoning"] = dict(model["reasoning"])
                model["item"] = await self._save(model["operation_id"], "assistant", "message", model["item"])
                events.append(self._content_event("reasoning.done", event, model, index, extension=True, text=text))
            elif block_type == "tool_call":
                call_id = str(block["id"])
                item = await self._save(
                    model["operation_id"],
                    "assistant",
                    f"call:{call_id}",
                    {
                        "type": "function_call",
                        "name": block["name"],
                        "arguments": block.get("args", {}),
                        "call_id": call_id,
                        "status": "in_progress",
                    },
                    content_index=index,
                )
                self.calls[call_id] = (model["operation_id"], f"call:{call_id}", item)
                events.append(
                    self._event(
                        "agent.session.turn.item.added",
                        self._source_id(event, f"call:{call_id}"),
                        output_index=item["yuxi"]["output_index"],
                        item=item,
                    )
                )
            return events
        if kind == "message-finish" and model["item"] is not None:
            model["item"]["status"] = "completed"
            model["item"] = await self._save(model["operation_id"], "assistant", "message", model["item"])
        return events

    async def _tool(self, event: dict, data: dict) -> list[dict]:
        """参数生成与执行结果分别发布，各自保持稳定身份。"""
        kind = data.get("event")
        call_id = str(data.get("tool_call_id") or "")
        if kind == "tool-started":
            item = await self._save(
                call_id,
                "tool",
                "output",
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": None,
                    "error": None,
                    "status": "in_progress",
                },
            )
            return [
                self._event(
                    "agent.session.turn.item.added",
                    self._source_id(event, "tool-output"),
                    output_index=item["yuxi"]["output_index"],
                    item=item,
                )
            ]
        # 原生 tool-error 也可能是 GraphInterrupt；结局由已提交 Run 决定。
        if kind != "tool-finished":
            return []
        result = data["result"]
        content = result.public_content
        error = result.error
        failed = error is not None
        item = await self._save(
            call_id,
            "tool",
            "output",
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": content,
                "error": error,
                "status": "failed" if failed else "completed",
            },
        )
        events = []
        if call_id in self.calls:
            operation, key, call = self.calls[call_id]
            call = await self._save(operation, "assistant", key, {**call, "status": item["status"]})
        else:
            async with pg_manager.get_async_session_context() as db:
                call = await PublicItemRepository(db).resumed_call(run_id=self.run_id, call_id=call_id)
        events.append(
            self._event(
                "agent.session.turn.item.done",
                self._source_id(event, "call-done"),
                output_index=call["yuxi"]["output_index"],
                item=call,
            )
        )
        events.append(
            self._event(
                "agent.session.turn.item.done",
                self._source_id(event, "output-done"),
                output_index=item["yuxi"]["output_index"],
                item=item,
            )
        )
        return events

    async def _ensure_message(self, model: dict, event: dict) -> list[dict]:
        """首个正文或推理块登记 message item。"""
        if model["item"] is not None:
            return []
        model["item"] = await self._save(
            model["operation_id"],
            "assistant",
            "message",
            {
                "type": "message",
                "role": "assistant",
                "content": [],
                "phase": "commentary",
                "status": "in_progress",
            },
        )
        item = model["item"]
        return [
            self._event(
                "agent.session.turn.item.added",
                self._source_id(event, "message"),
                output_index=item["yuxi"]["output_index"],
                item=item,
            )
        ]

    async def _ensure_text_block(self, model: dict, event: dict, index: int) -> list[dict]:
        """保留上游内容块位置，正文索引独立于工具和原始推理块。"""
        events = await self._ensure_message(model, event)
        if index not in model["blocks"]:
            content_index = len(model["blocks"])
            model["blocks"][index] = content_index
            model["item"]["yuxi"]["content_blocks"] = dict(model["blocks"])
            part = {"type": "output_text", "text": ""}
            model["item"]["content"].append(part)
            events.append(self._content_event("content_part.added", event, model, content_index, part=part))
        return events

    async def _save(self, operation_id: str, role: str, key: str, item: dict, content_index: int | None = None) -> dict:
        """边界快照提交后才允许发送 added/done。"""
        async with pg_manager.get_async_session_context() as db:
            return await PublicItemRepository(db).save(
                run_id=self.run_id,
                worker_id=self.worker_id,
                operation_id=operation_id,
                role=role,
                key=key,
                item=item,
                content_index=content_index,
            )

    def _content_event(self, name: str, source: dict, model: dict, content_index: int, extension: bool = False, **fields) -> dict:
        """输出内容块事件，共用 message 身份与递增索引。"""
        item = model["item"]
        prefix = "yuxi.session.turn." if extension else "agent.session.turn."
        return self._event(
            prefix + name,
            self._source_id(source, name),
            item_id=item["id"],
            output_index=item["yuxi"]["output_index"],
            content_index=content_index,
            **fields,
        )

    def _event(self, kind: str, identity: str, **fields) -> dict:
        """逻辑事件 ID 与订阅 cursor 分离，Redis 重放保持 ID。"""
        yuxi = {"run_id": self.run_id}
        return deepcopy(
            {
                "type": kind,
                "event_id": hash_id("event_", f"{self.run_id}:{self.worker_id}:{identity}", length=64),
                "session_id": self.thread_id,
                "turn_id": self.turn_id,
                "yuxi": yuxi,
                **fields,
            }
        )

    @staticmethod
    def _source_id(event: dict, suffix: str) -> str:
        """使用原生执行序号派生逻辑身份。"""
        return f"{event['seq']}:{suffix}"

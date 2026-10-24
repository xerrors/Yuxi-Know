"""Yuxi Agent 的 Token 用量观测中间件。

在每次主模型调用后估算近似上下文占用，并持久化 Provider 返回的实际
usage_metadata，按配置模型分桶累计到 Run 与 Thread 两级；快照写入
LangGraph state 供状态面板读取，便于展示与核对真实账单。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import Any, NotRequired, TypedDict

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ExtendedModelResponse,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.messages.ai import UsageMetadata, add_usage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.types import Command

from yuxi.modules.models.providers.builtin import USAGE_UNTRUSTED_PROVIDER_IDS
from yuxi.modules.models.providers.cache import model_cache

ZERO_TOTAL = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
TOKEN_USAGE_CONTEXT_FIELDS = frozenset(
    {
        "state_message_count",
        "state_message_count_before_call",
        "state_messages_tokens",
        "state_messages_tokens_before_call",
        "llm_message_count",
        "llm_messages_tokens",
        "llm_content_message_count",
        "llm_content_message_tokens",
        "llm_tool_message_count",
        "llm_tool_message_tokens",
        "llm_input_tokens",
        "next_llm_input_tokens",
        "system_tokens",
        "tools_tokens",
        "tool_count",
        "context_window",
        "context_usage_ratio",
        "remaining_context_tokens",
        "summary_active",
        "summary_message_tokens",
        "summary_trigger_tokens",
        "summary_pressure_ratio",
        "counter",
        "estimate",
        "measured_at",
    }
)


class TokenUsagePayload(TypedDict, total=False):
    """可序列化的 Token 用量快照，存入 LangGraph state。"""

    state_message_count: int
    state_message_count_before_call: int
    state_messages_tokens: int
    state_messages_tokens_before_call: int
    llm_message_count: int
    llm_messages_tokens: int
    llm_content_message_count: int
    llm_content_message_tokens: int
    llm_tool_message_count: int
    llm_tool_message_tokens: int
    llm_input_tokens: int
    next_llm_input_tokens: int
    system_tokens: int
    tools_tokens: int
    tool_count: int
    context_window: int | None
    context_usage_ratio: float | None
    remaining_context_tokens: int | None
    summary_active: bool
    summary_message_tokens: int
    summary_trigger_tokens: int | None
    summary_pressure_ratio: float | None
    current_run_id: str
    latest: dict[str, Any] | None
    run: dict[str, Any]
    thread: dict[str, Any]
    counter: str
    estimate: bool
    measured_at: str


class TokenUsageState(AgentState):
    """扩展 Agent state，携带最新的 Token 用量快照。"""

    token_usage: NotRequired[TokenUsagePayload]


class TokenUsageMiddleware(AgentMiddleware[TokenUsageState]):
    """观测主模型调用并记录近似上下文与实际 Token 用量。

    ``wrap_model_call`` 在每次模型调用后构建用量快照写入 state；快照同时
    保留上下文估算字段（``TOKEN_USAGE_CONTEXT_FIELDS``）与按模型分桶的
    Run/Thread 累计聚合。``before_agent`` 在 Run 入口重置 Run 级累计，
    并剔除用量不可信 Provider（见 providers.builtin）的历史用量桶。
    """

    state_schema = TokenUsageState

    def __init__(self, token_counter=count_tokens_approximately) -> None:
        super().__init__()
        self.token_counter = token_counter

    def before_agent(self, state: TokenUsageState, runtime: Any) -> dict[str, Any] | None:
        """在 Run 入口重置 Run 级用量，同时保留 v2 线程累计。"""
        run_id = str(getattr(runtime.context, "run_id", None) or "")
        previous = state.get("token_usage")
        previous = previous if isinstance(previous, Mapping) else {}
        same_run = previous.get("current_run_id") == run_id and isinstance(previous.get("run"), Mapping)
        context_fields = {key: previous[key] for key in TOKEN_USAGE_CONTEXT_FIELDS if key in previous}
        latest = previous.get("latest") if same_run else None
        if isinstance(latest, Mapping):
            latest_model = latest.get("model")
            latest_bucket_key = latest.get("bucket_key")
            latest_provider_id = latest_model.get("provider_id") if isinstance(latest_model, Mapping) else None
            if latest_provider_id in USAGE_UNTRUSTED_PROVIDER_IDS or (
                isinstance(latest_bucket_key, str) and latest_bucket_key.split(":", 1)[0] in USAGE_UNTRUSTED_PROVIDER_IDS
            ):
                latest = None
        return {
            "token_usage": {
                **context_fields,
                "current_run_id": run_id,
                "latest": latest,
                "run": _without_untrusted_providers(previous.get("run")) if same_run else _empty_aggregate(),
                "thread": _without_untrusted_providers(previous.get("thread")),
            }
        }

    async def abefore_agent(self, state: TokenUsageState, runtime: Any) -> dict[str, Any] | None:
        """异步入口复用同步 Run 初始化逻辑。"""
        return self.before_agent(state, runtime)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ExtendedModelResponse:
        response = handler(request)
        return ExtendedModelResponse(
            model_response=response,
            command=Command(update={"token_usage": self._build_snapshot(request, response)}),
        )

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ExtendedModelResponse:
        response = await handler(request)
        return ExtendedModelResponse(
            model_response=response,
            command=Command(update={"token_usage": self._build_snapshot(request, response)}),
        )

    def _build_snapshot(self, request: ModelRequest, response: ModelResponse) -> TokenUsagePayload:
        """根据单次模型请求与响应构建完整用量快照。"""
        state_messages = list(request.state.get("messages") or [])
        llm_messages = list(request.messages or [])
        system_messages = [request.system_message] if request.system_message is not None else []
        tools = list(request.tools or [])
        response_messages = list(response.result or [])

        state_tokens_before_call = self._count_tokens(state_messages)
        next_state_messages = [*state_messages, *response_messages]
        state_messages_tokens = self._count_tokens(next_state_messages)
        llm_messages_tokens = self._count_tokens(llm_messages)
        system_tokens = self._count_tokens(system_messages)
        tools_tokens = self._count_tokens([], tools=tools) if tools else 0
        llm_input_tokens = self._count_tokens([*system_messages, *llm_messages], tools=tools)
        next_llm_input_tokens = self._count_tokens(
            [*system_messages, *llm_messages, *response_messages],
            tools=tools,
        )

        context_window = _model_context_window(request.model)
        context_usage_ratio = None
        remaining_context_tokens = None
        if context_window:
            context_usage_ratio = min(1.0, round(llm_input_tokens / context_window, 4))
            remaining_context_tokens = max(context_window - llm_input_tokens, 0)

        summary_message = llm_messages[0] if llm_messages and _is_summary_message(llm_messages[0]) else None
        llm_tool_messages = [message for message in llm_messages if _is_tool_message(message)]
        llm_content_messages = [message for message in llm_messages if not _is_tool_message(message) and not _is_summary_message(message)]
        summary_trigger_tokens = _summary_trigger_tokens(getattr(request.runtime, "context", None))
        summary_pressure_ratio = round(next_llm_input_tokens / summary_trigger_tokens, 4) if summary_trigger_tokens else None
        previous_snapshot = request.state.get("token_usage")
        previous_snapshot = previous_snapshot if isinstance(previous_snapshot, Mapping) else {}
        model_usage = _model_usage_from_response(response)
        identity = _model_identity(request, response)
        runtime_context = getattr(request.runtime, "context", None)
        run_id = str(getattr(runtime_context, "run_id", None) or "")
        previous_run = previous_snapshot.get("run") if previous_snapshot.get("current_run_id") == run_id else None
        measured_at = datetime.now(UTC).isoformat()
        latest_usage = None
        run_usage = _without_untrusted_providers(previous_run if isinstance(previous_run, Mapping) else _empty_aggregate())
        thread_usage = _without_untrusted_providers(previous_snapshot.get("thread"))

        if identity.get("provider_id") not in USAGE_UNTRUSTED_PROVIDER_IDS:
            bucket_key, identity_source = _bucket_key(identity, request.model)
            run_usage = _add_call_to_aggregate(
                run_usage,
                bucket_key=bucket_key,
                identity_source=identity_source,
                identity=identity,
                usage=model_usage,
            )
            thread_usage = _add_call_to_aggregate(
                thread_usage,
                bucket_key=bucket_key,
                identity_source=identity_source,
                identity=identity,
                usage=model_usage,
            )
            cache_read_tokens = _cache_read_tokens(model_usage)
            input_tokens = _usage_input_tokens(model_usage)
            latest_usage = {
                "bucket_key": bucket_key,
                "model": identity,
                "usage": model_usage or {},
                "uncached_input_tokens": (max(input_tokens - cache_read_tokens, 0) if cache_read_tokens is not None else None),
                "cache_hit_ratio": (_ratio(cache_read_tokens, input_tokens) if cache_read_tokens is not None else None),
                "measured_at": measured_at,
            }
        else:
            run_usage = _add_unavailable_call(run_usage)
            thread_usage = _add_unavailable_call(thread_usage)

        return {
            "state_message_count": len(next_state_messages),
            "state_message_count_before_call": len(state_messages),
            "state_messages_tokens": state_messages_tokens,
            "state_messages_tokens_before_call": state_tokens_before_call,
            "llm_message_count": len(llm_messages),
            "llm_messages_tokens": llm_messages_tokens,
            "llm_content_message_count": len(llm_content_messages),
            "llm_content_message_tokens": self._count_tokens(llm_content_messages),
            "llm_tool_message_count": len(llm_tool_messages),
            "llm_tool_message_tokens": self._count_tokens(llm_tool_messages),
            "llm_input_tokens": llm_input_tokens,
            "next_llm_input_tokens": next_llm_input_tokens,
            "system_tokens": system_tokens,
            "tools_tokens": tools_tokens,
            "tool_count": len(tools),
            "context_window": context_window,
            "context_usage_ratio": context_usage_ratio,
            "remaining_context_tokens": remaining_context_tokens,
            "summary_active": summary_message is not None,
            "summary_message_tokens": self._count_tokens([summary_message]) if summary_message else 0,
            "summary_trigger_tokens": summary_trigger_tokens,
            "summary_pressure_ratio": summary_pressure_ratio,
            "current_run_id": run_id,
            "latest": latest_usage,
            "run": run_usage,
            "thread": thread_usage,
            "counter": "langchain.count_tokens_approximately",
            "estimate": True,
            "measured_at": measured_at,
        }

    def _count_tokens(self, messages: Iterable[Any], *, tools: list[Any] | None = None) -> int:
        message_list = list(messages)
        if tools is not None:
            return int(self.token_counter(message_list, tools=tools))
        return int(self.token_counter(message_list))


def _safe_int(value: Any) -> int | None:
    """将数值安全转换为 int，bool 与非整数值返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _ratio(numerator: int, denominator: int) -> float | None:
    """计算比例，分母为 0 时返回 None 而非抛出除零异常。"""
    return round(numerator / denominator, 4) if denominator > 0 else None


def _empty_aggregate() -> dict[str, Any]:
    """构造一个空的 v2 聚合结构，作为 Run/Thread 用量的初始状态。"""
    return {
        "schema_version": 2,
        "model_call_count": 0,
        "usage_reported_call_count": 0,
        "usage_unavailable_call_count": 0,
        "complete": False,
        "models": {},
        "total": dict(ZERO_TOTAL),
    }


def _aggregate_from_state(value: Any) -> dict[str, Any]:
    """校验并规整从 state 读取的聚合结构，schema_version 不匹配时回退为空聚合。"""
    if not isinstance(value, Mapping) or value.get("schema_version") != 2:
        return _empty_aggregate()
    models = value.get("models")
    total = value.get("total")
    return {
        "schema_version": 2,
        "model_call_count": _safe_int(value.get("model_call_count")) or 0,
        "usage_reported_call_count": _safe_int(value.get("usage_reported_call_count")) or 0,
        "usage_unavailable_call_count": _safe_int(value.get("usage_unavailable_call_count")) or 0,
        "complete": value.get("complete") is True,
        "models": {str(key): dict(bucket) for key, bucket in models.items() if isinstance(bucket, Mapping)}
        if isinstance(models, Mapping)
        else {},
        "total": dict(total) if isinstance(total, Mapping) else dict(ZERO_TOTAL),
    }


def _recompute_aggregate_totals(aggregate: dict[str, Any]) -> None:
    """根据当前 models 重算聚合级计数和 total。"""
    models = aggregate["models"]
    model_call_count = sum(_safe_int(bucket.get("model_call_count")) or 0 for bucket in models.values() if isinstance(bucket, Mapping))
    usage_reported_call_count = sum(
        _safe_int(bucket.get("usage_reported_call_count")) or 0 for bucket in models.values() if isinstance(bucket, Mapping)
    )
    usage_unavailable_call_count = _safe_int(aggregate.get("usage_unavailable_call_count")) or 0
    aggregate["model_call_count"] = model_call_count + usage_unavailable_call_count
    aggregate["usage_reported_call_count"] = usage_reported_call_count
    aggregate["complete"] = aggregate["model_call_count"] > 0 and (usage_reported_call_count == aggregate["model_call_count"])
    total = dict(ZERO_TOTAL)
    for bucket in models.values():
        if not isinstance(bucket, Mapping):
            continue
        bucket_usage = bucket.get("usage")
        if not isinstance(bucket_usage, Mapping):
            continue
        for key in total:
            total[key] += _safe_int(bucket_usage.get(key)) or 0
    aggregate["total"] = total


def _add_unavailable_call(aggregate: Mapping[str, Any]) -> dict[str, Any]:
    """记录一次无法获得可信 Provider usage 的模型调用。"""
    result = _aggregate_from_state(aggregate)
    result["usage_unavailable_call_count"] += 1
    _recompute_aggregate_totals(result)
    return result


def _without_untrusted_providers(aggregate: Mapping[str, Any]) -> dict[str, Any]:
    """移除历史 checkpoint 中用量不可信 Provider 的错误用量桶。"""
    result = _aggregate_from_state(aggregate)
    result["models"] = {
        key: bucket
        for key, bucket in result["models"].items()
        if not (isinstance(bucket.get("model"), Mapping) and bucket["model"].get("provider_id") in USAGE_UNTRUSTED_PROVIDER_IDS)
    }
    _recompute_aggregate_totals(result)
    return result


def _bucket_key(identity: Mapping[str, str], model: Any) -> tuple[str, str]:
    """按优先级选取用量分桶 key：配置的 model spec > 响应携带的 model id > 适配器兜底标识。"""
    configured_spec = identity.get("configured_model_spec")
    if configured_spec:
        return configured_spec, "configured_metadata"
    response_model_id = identity.get("response_model_id")
    provider_type = identity.get("provider_type") or "unknown"
    if response_model_id:
        return f"response:{provider_type}:{response_model_id}", "response_metadata"
    model_id = getattr(model, "model_name", None) or getattr(model, "model", None) or "unknown"
    return f"unattributed:{model.__class__.__name__}:{model_id}", "adapter_fallback"


def _add_call_to_aggregate(
    aggregate: Mapping[str, Any],
    *,
    bucket_key: str,
    identity_source: str,
    identity: Mapping[str, str],
    usage: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """把一次模型调用的 usage 累加进指定分桶，同时更新缓存命中统计和聚合总计。"""
    result = _aggregate_from_state(aggregate)
    models = result["models"]
    previous_bucket = models.get(bucket_key)
    previous_bucket = dict(previous_bucket) if isinstance(previous_bucket, Mapping) else {}
    usage_increment = _usage_for_accumulation(usage)
    previous_usage = previous_bucket.get("usage")
    previous_usage = _usage_for_accumulation(previous_usage) if isinstance(previous_usage, Mapping) else None
    cumulative_usage = add_usage(previous_usage, usage_increment) if usage_increment else previous_usage

    model_identity = previous_bucket.get("model")
    model_identity = dict(model_identity) if isinstance(model_identity, Mapping) else {}
    model_identity.update({key: value for key, value in identity.items() if key != "response_model_id"})
    model_identity["identity_source"] = identity_source
    response_model_ids = model_identity.get("response_model_ids")
    response_model_ids = list(response_model_ids) if isinstance(response_model_ids, list) else []
    response_model_id = identity.get("response_model_id")
    if response_model_id and response_model_id not in response_model_ids:
        response_model_ids.append(response_model_id)
    model_identity["response_model_ids"] = response_model_ids

    cache_read = _cache_read_tokens(usage)
    cache_observed = cache_read is not None
    cache_observed_calls = (_safe_int(previous_bucket.get("cache_observed_call_count")) or 0) + int(cache_observed)
    cache_hit_calls = (_safe_int(previous_bucket.get("cache_hit_call_count")) or 0) + int(cache_read is not None and cache_read > 0)
    observed_input = (_safe_int(previous_bucket.get("cache_observed_input_tokens")) or 0) + (
        _usage_input_tokens(usage) if cache_observed else 0
    )
    cache_read_input = (_safe_int(previous_bucket.get("cache_read_input_tokens")) or 0) + (cache_read or 0)

    models[bucket_key] = {
        "model": model_identity,
        "usage": cumulative_usage or {},
        "model_call_count": (_safe_int(previous_bucket.get("model_call_count")) or 0) + 1,
        "usage_reported_call_count": (_safe_int(previous_bucket.get("usage_reported_call_count")) or 0) + int(usage_increment is not None),
        "cache_observed_call_count": cache_observed_calls,
        "cache_hit_call_count": cache_hit_calls,
        "cache_observed_input_tokens": observed_input,
        "cache_read_input_tokens": cache_read_input,
        "uncached_input_tokens": max(observed_input - cache_read_input, 0) if cache_observed_calls else None,
        "cache_hit_ratio": _ratio(cache_read_input, observed_input),
        "cache_request_hit_ratio": _ratio(cache_hit_calls, cache_observed_calls),
    }

    _recompute_aggregate_totals(result)
    return result


def _model_context_window(model: Any) -> int | None:
    """读取模型配置的上下文窗口大小，未配置或非法时返回 None。"""
    profile = getattr(model, "profile", None)
    if not isinstance(profile, Mapping):
        return None
    max_input_tokens = profile.get("max_input_tokens")
    return max_input_tokens if isinstance(max_input_tokens, int) and max_input_tokens > 0 else None


def _summary_trigger_tokens(runtime_context: Any) -> int | None:
    """读取运行时上下文的摘要触发阈值并转换为 token 数，未配置时返回 None。"""
    threshold = _safe_int(getattr(runtime_context, "summary_threshold", None))
    if threshold is None or threshold <= 0:
        return None
    return threshold * 1024


def _is_summary_message(message: AnyMessage) -> bool:
    """判断消息是否为摘要中间件产生的摘要消息。"""
    return getattr(message, "additional_kwargs", {}).get("lc_source") == "summarization"


def _is_tool_message(message: AnyMessage) -> bool:
    """判断消息是否为工具消息。"""
    return getattr(message, "type", None) == "tool" or getattr(message, "role", None) == "tool"


def _ai_message_from_response(response: ModelResponse) -> AIMessage | None:
    """从模型响应结果中取最后一条 AIMessage。"""
    for message in reversed(response.result):
        if isinstance(message, AIMessage):
            return message
    return None


def _model_usage_from_response(response: ModelResponse) -> dict[str, Any] | None:
    """提取响应中 AIMessage 携带的原始 usage_metadata。"""
    message = _ai_message_from_response(response)
    usage = getattr(message, "usage_metadata", None) if message else None
    return dict(usage) if isinstance(usage, Mapping) else None


def _usage_for_accumulation(usage: Mapping[str, Any] | None) -> UsageMetadata | None:
    """保留可累计的数值 token 字段，忽略 Provider 的非数值扩展元数据。"""
    if not usage:
        return None

    normalized: dict[str, Any] = {}
    for key, value in usage.items():
        if isinstance(value, int) and not isinstance(value, bool):
            normalized[str(key)] = value
            continue
        if isinstance(value, Mapping):
            details = {
                str(detail_key): detail_value
                for detail_key, detail_value in value.items()
                if isinstance(detail_value, int) and not isinstance(detail_value, bool)
            }
            if details:
                normalized[str(key)] = details

    required_keys = ("input_tokens", "output_tokens", "total_tokens")
    if not all(isinstance(normalized.get(key), int) for key in required_keys):
        return None
    return normalized  # type: ignore[return-value]


def _usage_input_tokens(usage: Mapping[str, Any] | None) -> int:
    """读取 usage 中的 input_tokens，缺失或非法时返回 0。"""
    value = usage.get("input_tokens") if usage else None
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _cache_read_tokens(usage: Mapping[str, Any] | None) -> int | None:
    """按优先级从 input_token_details 中读取缓存命中 token 数，未观测到缓存字段时返回 None。"""
    details = usage.get("input_token_details") if usage else None
    if not isinstance(details, Mapping):
        return None
    for key in ("cache_read", "priority_cache_read", "flex_cache_read"):
        if key not in details:
            continue
        value = details.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else None
    return None


def _model_identity(request: ModelRequest, response: ModelResponse) -> dict[str, str]:
    """依次从模型元数据、运行时上下文配置的 model spec、model_cache 和响应元数据解析模型身份信息。"""
    model_metadata = getattr(request.model, "metadata", None) or {}
    runtime_context = getattr(request.runtime, "context", None)
    configured_spec = getattr(runtime_context, "model", None)
    configured_spec = configured_spec.strip() if isinstance(configured_spec, str) else ""

    identity: dict[str, str] = {}
    for key, meta_key in (
        ("provider_id", "yuxi_provider_id"),
        ("provider_type", "yuxi_provider_type"),
        ("configured_model_id", "yuxi_model_id"),
        ("configured_model_spec", "yuxi_model_spec"),
    ):
        value = model_metadata.get(meta_key)
        if isinstance(value, str) and value:
            identity[key] = value

    if not identity and configured_spec:
        model_info = model_cache.get_model_info(configured_spec)
        if model_info:
            identity = {
                "provider_id": model_info.provider_id,
                "provider_type": model_info.provider_type,
                "configured_model_id": model_info.model_id,
                "configured_model_spec": model_info.spec,
            }
        else:
            identity["configured_model_spec"] = configured_spec
    elif configured_spec:
        identity["configured_model_spec"] = configured_spec

    message = _ai_message_from_response(response)
    response_metadata = getattr(message, "response_metadata", None) if message else None
    if isinstance(response_metadata, Mapping):
        response_model_id = response_metadata.get("model_name") or response_metadata.get("model")
        if isinstance(response_model_id, str) and response_model_id:
            identity["response_model_id"] = response_model_id
        if "provider_type" not in identity:
            response_provider = response_metadata.get("model_provider")
            if isinstance(response_provider, str) and response_provider:
                identity["provider_type"] = response_provider

    return identity

"""Agent 压测脚本的纯逻辑与协议负向测试。"""

from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import httpx

from test.performance.__main__ import build_parser
from test.performance.load import (
    AgentLoadClient,
    LoadTestError,
    LocalResourceSampler,
    TaskResult,
    ToolEvidence,
    _parse_memory_mb,
    contains_model_output,
    evaluate_result,
    first_model_request_latency_ms,
    iter_sse,
    observe_tool_evidence,
    parse_concurrency,
    record_run_timing,
    summarize,
    write_results,
)


async def _lines(*items: str):
    for item in items:
        yield item


class AgentLoadTestScriptTest(unittest.IsolatedAsyncioTestCase):
    """验证脚本不会把错误协议或缺失工具执行误报为成功。"""

    async def test_iter_sse_parses_json_and_ignores_heartbeat(self) -> None:
        events = [
            event
            async for event in iter_sse(
                _lines(
                    ": heartbeat",
                    "",
                    "id: 1-0",
                    "event: yuxi.session.run.created",
                    'data: {"session_id":"thread-1",',
                    'data: "input_id":"input-1","turn_id":"turn-1","yuxi":{"run_id":"run-1"}}',
                    "",
                )
            )
        ]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].name, "yuxi.session.run.created")
        self.assertEqual(events[0].event_id, "1-0")
        self.assertEqual(events[0].data["yuxi"]["run_id"], "run-1")

    async def test_iter_sse_rejects_non_json_data(self) -> None:
        with self.assertRaises(LoadTestError):
            async for _ in iter_sse(_lines("event: end", "data: not-json", "")):
                pass

    async def test_thread_sse_returns_only_target_input_run(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/v1/agents/sessions/thread-1/events")
            return httpx.Response(
                200,
                text=(
                    "event: yuxi.session.run.created\n"
                    'data: {"session_id":"thread-1","input_id":"neighbor","turn_id":"other",'
                    '"yuxi":{"run_id":"other"}}\n\n'
                    "event: yuxi.session.run.created\n"
                    'data: {"session_id":"thread-1","input_id":"input-1","turn_id":"turn-1",'
                    '"yuxi":{"run_id":"run-1"}}\n\n'
                ),
            )

        async with httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler)) as client:
            load_client = AgentLoadClient(client, {}, 10)
            run_id, turn_id = await load_client.wait_for_run_id("thread-1", "input-1")

        self.assertEqual((run_id, turn_id), ("run-1", "turn-1"))

    async def test_thread_sse_rejects_neighbor_thread(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                text=(
                    'event: yuxi.session.run.created\ndata: {"session_id":"other","input_id":"input-1",'
                    '"turn_id":"turn-2","yuxi":{"run_id":"run-2"}}\n\n'
                ),
            )

        async with httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler)) as client:
            load_client = AgentLoadClient(client, {}, 10)
            with self.assertRaises(LoadTestError):
                await load_client.wait_for_run_id("thread-1", "input-1")

    async def test_public_input_submission_preserves_thread_and_key(self) -> None:
        """压测输入走 Public Thread 事件协议。"""

        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/v1/agents/sessions/thread-1/events")
            self.assertEqual(request.headers["Idempotency-Key"], "load-event")
            event = json.loads(request.content)["events"][0]
            self.assertEqual((event["type"], event["yuxi"]["mode"]), ("agent.session.input.message", "follow_up"))
            self.assertEqual(event["input"][0]["content"][0]["text"], "say hi")
            return httpx.Response(202, json={"thread_id": "thread-1", "input_id": "input-1"})

        async with httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler)) as client:
            payload, duration = await AgentLoadClient(client, {}, 10).submit_input(
                thread_id="thread-1", event_key="load-event", prompt="say hi"
            )
        self.assertEqual(payload["input_id"], "input-1")
        self.assertGreaterEqual(duration, 0)

    async def test_load_thread_cleanup_uses_public_archive(self) -> None:
        """压测会话清理由 Public Thread 归档协议完成。"""

        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path, "/api/v1/agents/sessions/thread-1/archive")
            return httpx.Response(200, json={"status": "archived"})

        async with httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler)) as client:
            await AgentLoadClient(client, {}, 10).archive_thread("thread-1")

    def test_sandbox_result_requires_execute_completion_marker(self) -> None:
        payload = {
            "id": "run-1",
            "input_id": "input-1",
            "turn_id": "turn-1",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "LOAD_TEST_OK"}],
                    "turn_id": "turn-1",
                    "yuxi": {"run_id": "run-1"},
                }
            ],
        }

        success, error, _ = evaluate_result(
            scenario="sandbox",
            payload=payload,
            input_id="input-1",
            turn_id="turn-1",
            run_id="run-1",
            turn_payload={
                "id": "turn-1",
                "object": "agent.session.turn",
                "status": "completed",
                "yuxi": {"result_run_id": "run-1"},
            },
            evidence=ToolEvidence(execute_started=True, execute_finished=True, output_marker_seen=False),
        )

        self.assertFalse(success)
        self.assertIn("LOAD_TEST_TOOL_OK", error or "")

    def test_function_output_proves_execute_completion(self):
        evidence = ToolEvidence(execute_started=True, call_ids={"execute-call"})
        observe_tool_evidence(
            {
                "type": "agent.session.turn.item.done",
                "item": {
                    "type": "function_call_output",
                    "call_id": "execute-call",
                    "status": "completed",
                    "output": "LOAD_TEST_TOOL_OK",
                },
            },
            evidence,
        )
        self.assertTrue(evidence.execute_finished)
        self.assertTrue(evidence.output_marker_seen)

    def test_first_model_output_accepts_text_and_full_function_call(self):
        self.assertTrue(contains_model_output({"type": "agent.session.turn.output_text.delta", "delta": "你"}))
        self.assertTrue(
            contains_model_output({"type": "agent.session.turn.item.added", "item": {"type": "function_call", "arguments": {}}})
        )

    def test_metadata_does_not_count_as_first_model_output(self) -> None:
        self.assertFalse(
            contains_model_output(
                {
                    "run_id": "run-1",
                    "payload": {"run_type": "chat", "source": "agent_load_test"},
                }
            )
        )

    def test_first_model_request_latency_uses_result_timing(self) -> None:
        started_at = datetime.fromisoformat("2026-09-05T10:00:00+00:00")
        self.assertEqual(
            first_model_request_latency_ms(
                started_at,
                {"timing": {"first_model_request_at": "2026-09-05T10:00:01.250000Z"}},
            ),
            1250.0,
        )

    def test_first_model_request_latency_is_unknown_without_callback_timestamp(
        self,
    ) -> None:
        started_at = datetime.fromisoformat("2026-09-05T10:00:00+00:00")
        self.assertIsNone(first_model_request_latency_ms(started_at, {"timing": {}}))

    def test_run_creation_timing_is_distinct_from_client_submit(self) -> None:
        started_at = datetime.fromisoformat("2026-09-05T10:00:00+00:00")
        timing = {
            "created_at": "2026-09-05T10:00:00.250000Z",
            "first_model_request_at": "2026-09-05T10:00:01.250000Z",
            "first_model_request_latency_ms": 1000.0,
        }
        result = TaskResult(level=10, task_index=1, event_key="timing-test")
        record_run_timing(result, started_at, {"timing": timing})
        self.assertEqual(result.first_model_request_ms, 1250.0)
        self.assertEqual(result.created_to_first_model_request_ms, 1000.0)
        self.assertEqual(result.run_timing, timing)
        missing = TaskResult(level=10, task_index=2, event_key="missing-timing")
        record_run_timing(missing, started_at, {"timing": {}})
        summary = summarize([result, missing])[0]
        self.assertEqual(summary["created_to_first_model_request_p95_ms"], 1000.0)
        self.assertEqual(summary["missing_model_request_timing"], 1)

    def test_sandbox_result_accepts_same_run_with_tool_evidence(self) -> None:
        success, error, output_chars = evaluate_result(
            scenario="sandbox",
            payload={
                "id": "run-1",
                "input_id": "input-1",
                "turn_id": "turn-1",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "LOAD_TEST_OK"}],
                        "turn_id": "turn-1",
                        "yuxi": {"run_id": "run-1"},
                    }
                ],
            },
            input_id="input-1",
            turn_id="turn-1",
            run_id="run-1",
            turn_payload={
                "id": "turn-1",
                "object": "agent.session.turn",
                "status": "completed",
                "yuxi": {"result_run_id": "run-1"},
            },
            evidence=ToolEvidence(execute_started=True, execute_finished=True, output_marker_seen=True),
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(output_chars, len("LOAD_TEST_OK"))

    def test_result_rejects_neighbor_run(self) -> None:
        success, error, _ = evaluate_result(
            scenario="sandbox",
            payload={
                "id": "run-neighbor",
                "input_id": "input-1",
                "turn_id": "turn-1",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "LOAD_TEST_OK"}],
                        "turn_id": "turn-1",
                        "yuxi": {"run_id": "run-neighbor"},
                    }
                ],
            },
            input_id="input-1",
            turn_id="turn-1",
            run_id="run-1",
            turn_payload={
                "id": "turn-1",
                "object": "agent.session.turn",
                "status": "completed",
                "yuxi": {"result_run_id": "run-1"},
            },
            evidence=ToolEvidence(execute_started=True, execute_finished=True, output_marker_seen=True),
        )

        self.assertFalse(success)
        self.assertIn("Run 结果", error or "")

    def test_parse_concurrency_rejects_out_of_range_value(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_concurrency("1,501")

    def test_exited_container_memory_is_skipped(self) -> None:
        self.assertIsNone(_parse_memory_mb("--"))
        self.assertAlmostEqual(_parse_memory_mb("1 GiB") or 0, 1024)

    def test_resource_sampler_only_counts_current_compose_services(self) -> None:
        """本机统计不把无关容器或远端 VM 当成零用量沙盒。"""
        sampler = LocalResourceSampler("project-one")
        stats = "\n".join(
            json.dumps(row)
            for row in [
                {"ID": "api-id", "Name": "api", "MemUsage": "64MiB / 1GiB", "CPUPerc": "5%"},
                {"ID": "other-id", "Name": "project-one-sandbox-old", "MemUsage": "128MiB / 1GiB", "CPUPerc": "90%"},
            ]
        )
        with patch("test.performance.load._run_local_command", return_value=stats):
            memory, cpu = sampler._container_stats({"api-id": "api"})
        self.assertEqual(memory, {"api": 64.0})
        self.assertEqual(cpu, {"api": 5.0})

    def test_parser_rejects_retired_docker_sandbox_options(self) -> None:
        """已删除的部署旋钮不能继续改变压测范围。"""
        for option in ("--sandbox-container-prefix", "--sandbox-network-prefix"):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(["load", option, "unused"])

    def test_summarize_uses_nearest_rank_and_counts_failures(self) -> None:
        summary = summarize(
            [
                TaskResult(level=2, task_index=1, event_key="a", success=True, total_ms=100),
                TaskResult(level=2, task_index=2, event_key="b", success=False, total_ms=300),
            ]
        )[0]

        self.assertEqual(summary["succeeded"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["success_rate"], 0.5)
        self.assertEqual(summary["total_p50_ms"], 100)
        self.assertEqual(summary["total_p95_ms"], 300)
        self.assertIn("request_queue_p95_ms", summary)
        self.assertIn("first_run_event_p95_ms", summary)
        self.assertIn("first_token_p95_ms", summary)

    def test_write_results_omits_credentials_and_full_output(self) -> None:
        result = TaskResult(
            level=1,
            task_index=1,
            event_key="request-1",
            run_id="run-1",
            success=True,
            output_chars=1234,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            json_path, csv_path, resources_path = write_results(
                output_dir=Path(tempdir),
                config={"scenario": "chat", "base_url": "http://test"},
                results=[result],
                summaries=summarize([result]),
            )
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            csv_text = csv_path.read_text(encoding="utf-8")
            resources_text = resources_path.read_text(encoding="utf-8")

        self.assertNotIn("output", payload["requests"][0])
        self.assertNotIn("authorization", json.dumps(payload).lower())
        self.assertNotIn("authorization", csv_text.lower())
        self.assertIn("host_available_memory_mb", resources_text)

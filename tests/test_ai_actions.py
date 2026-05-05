from pathlib import Path
import asyncio
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_actions import AiActionExecutor, AiActionRequest
from qqbot.services.codex_task_service import CodexProgressEvent, CodexTaskResult


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_api(self, api: str, **data: object) -> None:
        self.calls.append((api, data))


def test_send_private_message_allows_user_to_message_self(tmp_path: Path) -> None:
    bot = FakeBot()
    executor = AiActionExecutor(bot=bot, data_root=tmp_path)

    result = asyncio.run(
        executor.execute(
            AiActionRequest(
                action_type="send_private_message",
                actor_user_id="10001",
                target_user_id="10001",
                message="测试消息",
            )
        )
    )

    assert result.ok is True
    assert bot.calls == [("send_private_msg", {"user_id": 10001, "message": "测试消息"})]


def test_send_private_message_splits_long_text(tmp_path: Path) -> None:
    bot = FakeBot()
    executor = AiActionExecutor(bot=bot, data_root=tmp_path)

    result = asyncio.run(
        executor.execute(
            AiActionRequest(
                action_type="send_private_message",
                actor_user_id="10001",
                target_user_id="10001",
                message="long text " * 150,
            )
        )
    )

    assert result.ok is True
    assert [api for api, _ in bot.calls] == ["send_private_msg", "send_private_msg"]
    assert bot.calls[0][1]["message"].startswith("（1/2）\n")
    assert bot.calls[1][1]["message"].startswith("（2/2）\n")


def test_send_private_message_rejects_non_admin_targeting_other_user(tmp_path: Path) -> None:
    bot = FakeBot()
    executor = AiActionExecutor(bot=bot, data_root=tmp_path)

    result = asyncio.run(
        executor.execute(
            AiActionRequest(
                action_type="send_private_message",
                actor_user_id="10001",
                target_user_id="10002",
                message="测试消息",
            )
        )
    )

    assert result.ok is False
    assert "只能私聊自己" in result.message
    assert bot.calls == []


def test_schedule_once_records_task_and_audit(tmp_path: Path) -> None:
    bot = FakeBot()
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    tasks = []

    def task_factory(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    async def run() -> None:
        executor = AiActionExecutor(
            bot=bot,
            data_root=tmp_path,
            sleep=fake_sleep,
            task_factory=task_factory,
        )
        result = await executor.execute(
            AiActionRequest(
                action_type="schedule_once",
                actor_user_id="10001",
                delay_seconds=60,
                nested_action=AiActionRequest(
                    action_type="send_private_message",
                    actor_user_id="10001",
                    target_user_id="10001",
                    message="测试消息",
                ),
            )
        )
        assert result.ok is True
        await asyncio.gather(*tasks)

    asyncio.run(run())

    assert sleep_calls == [60.0]
    assert bot.calls == [("send_private_msg", {"user_id": 10001, "message": "测试消息"})]
    audit_path = tmp_path / "ai" / "actions" / "audit.jsonl"
    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [record["action_type"] for record in records] == [
        "schedule_once",
        "send_private_message",
    ]


def test_codex_task_is_admin_only(tmp_path: Path) -> None:
    bot = FakeBot()
    executor = AiActionExecutor(bot=bot, data_root=tmp_path)

    result = asyncio.run(
        executor.execute(
            AiActionRequest(
                action_type="run_codex_task",
                actor_user_id="10001",
                target_group_id="319567534",
                codex_project_id="mlj_dspmods",
                codex_prompt="修一下这个",
                codex_evidence="System.IndexOutOfRangeException FractionateEverything",
            )
        )
    )

    assert result.ok is False
    assert "管理员" in result.message


def test_codex_task_runs_in_background_and_reports_group(tmp_path: Path) -> None:
    bot = FakeBot()
    tasks = []
    requests = []

    def task_factory(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    async def fake_runner(request):
        requests.append(request)
        return CodexTaskResult(True, "已修改 BuildingManager。", exit_code=0)

    async def run() -> None:
        executor = AiActionExecutor(
            bot=bot,
            data_root=tmp_path,
            task_factory=task_factory,
            codex_runner=fake_runner,
        )
        result = await executor.execute(
            AiActionRequest(
                action_type="run_codex_task",
                actor_user_id="605738729",
                target_group_id="319567534",
                codex_project_id="mlj_dspmods",
                codex_prompt="修一下这个",
                codex_evidence="System.IndexOutOfRangeException FractionateEverything",
                is_admin=True,
            )
        )
        assert result.ok is True
        await asyncio.gather(*tasks)

    asyncio.run(run())

    assert requests[0].project.repo_path.endswith("MLJ_DSPmods")
    assert bot.calls[0] == (
        "send_group_msg",
        {
            "group_id": 319567534,
            "message": "已交给本地 Codex：MLJ_DSPmods\n正在启动并读取项目上下文。",
        },
    )
    assert bot.calls[1] == (
        "send_group_msg",
        {
            "group_id": 319567534,
            "message": "Codex 修复任务成功：MLJ_DSPmods\n已修改 BuildingManager。",
        },
    )


def test_codex_task_reports_long_group_result_as_forward_message(tmp_path: Path) -> None:
    bot = FakeBot()
    tasks = []

    def task_factory(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    async def fake_runner(request):
        return CodexTaskResult(True, "长回报 " * 500, exit_code=0)

    async def run() -> None:
        executor = AiActionExecutor(
            bot=bot,
            data_root=tmp_path,
            task_factory=task_factory,
            codex_runner=fake_runner,
        )
        result = await executor.execute(
            AiActionRequest(
                action_type="run_codex_task",
                actor_user_id="605738729",
                target_group_id="319567534",
                codex_project_id="mlj_dspmods",
                codex_prompt="修一下这个",
                is_admin=True,
            )
        )
        assert result.ok is True
        await asyncio.gather(*tasks)

    asyncio.run(run())

    assert bot.calls[0][0] == "send_group_msg"
    assert bot.calls[1][0] == "send_group_forward_msg"
    assert bot.calls[1][1]["messages"][0]["type"] == "node"
    assert "长回报" in bot.calls[1][1]["messages"][0]["data"]["content"]


def test_codex_task_reports_streaming_progress(tmp_path: Path) -> None:
    bot = FakeBot()
    tasks = []

    def task_factory(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    async def fake_runner(request):
        assert request.progress_callback is not None
        await request.progress_callback(
            CodexProgressEvent(phase="output", message="正在读取 AGENTS.md", stream="stdout")
        )
        await request.progress_callback(
            CodexProgressEvent(phase="output", message="这条会被节流", stream="stdout")
        )
        return CodexTaskResult(True, "完成", exit_code=0)

    async def run() -> None:
        executor = AiActionExecutor(
            bot=bot,
            data_root=tmp_path,
            task_factory=task_factory,
            codex_runner=fake_runner,
        )
        result = await executor.execute(
            AiActionRequest(
                action_type="run_codex_task",
                actor_user_id="605738729",
                target_group_id="319567534",
                codex_project_id="mlj_dspmods",
                codex_prompt="修一下这个",
                is_admin=True,
            )
        )
        assert result.ok is True
        await asyncio.gather(*tasks)

    asyncio.run(run())

    messages = [data["message"] for api, data in bot.calls if api == "send_group_msg"]
    assert any("正在读取 AGENTS.md" in message for message in messages)
    assert not any("这条会被节流" in message for message in messages)


def test_qqbot_codex_task_schedules_self_restart_after_group_report(tmp_path: Path) -> None:
    bot = FakeBot()
    tasks = []
    restart_calls = []

    def task_factory(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    async def fake_runner(request):
        return CodexTaskResult(True, "已修改 qqbot。", exit_code=0)

    async def run() -> None:
        executor = AiActionExecutor(
            bot=bot,
            data_root=tmp_path,
            sleep=lambda _seconds: asyncio.sleep(0),
            task_factory=task_factory,
            codex_runner=fake_runner,
            self_restart_scheduler=lambda: restart_calls.append("restart"),
        )
        result = await executor.execute(
            AiActionRequest(
                action_type="run_codex_task",
                actor_user_id="605738729",
                target_group_id="1163635014",
                codex_project_id="qqbot",
                codex_prompt="修一下机器人",
                is_admin=True,
            )
        )
        assert result.ok is True
        await asyncio.gather(*tasks)

    asyncio.run(run())

    assert restart_calls == ["restart"]
    assert bot.calls[0][0] == "send_group_msg"
    assert bot.calls[1][0] == "send_group_msg"
    assert "已安排 Bot 重启" in bot.calls[1][1]["message"]
    notices = tmp_path / "ai" / "codex_self_update_notices.json"
    assert "1163635014" in notices.read_text(encoding="utf-8")


def test_send_group_file_uploads_existing_file_for_admin(tmp_path: Path) -> None:
    bot = FakeBot()
    package = tmp_path / "ModZips" / "FractionateEverything_2.3.0.zip"
    package.parent.mkdir()
    package.write_bytes(b"zip")
    executor = AiActionExecutor(bot=bot, data_root=tmp_path)

    result = asyncio.run(
        executor.execute(
            AiActionRequest(
                action_type="send_group_file",
                actor_user_id="605738729",
                target_group_id="319567534",
                file_path=str(package),
                is_admin=True,
            )
        )
    )

    assert result.ok is True
    assert bot.calls == [
        (
            "upload_group_file",
            {
                "group_id": 319567534,
                "file": str(package),
                "name": "FractionateEverything_2.3.0.zip",
            },
        )
    ]

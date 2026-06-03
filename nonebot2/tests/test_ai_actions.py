from pathlib import Path
import asyncio
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_actions import AiActionExecutor, AiActionRequest


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

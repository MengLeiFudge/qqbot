from pathlib import Path
import asyncio
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.config import RuntimeSettings
from qqbot.services.ai_actions import AiActionExecutor, AiActionResult
from qqbot.services.ai_gateway import AiResponse
from qqbot.services.ai_reply_review_service import (
    AiReplyReviewService,
    build_auto_fix_prompt,
    parse_review_result,
)
from qqbot.services.group_message_log_store import GroupMessageLogStore


class FakeGateway:
    def __init__(self, text: str) -> None:
        self.text = text
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return AiResponse(self.text)


class FallbackGateway:
    def __init__(self) -> None:
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return AiResponse("timeout", fallback=True, fallback_reason="timeout")


class FakeExecutor:
    def __init__(self) -> None:
        self.requests = []

    async def execute(self, request):
        self.requests.append(request)
        return AiActionResult(True, "ok", request.action_type)


def test_parse_review_result_accepts_json() -> None:
    result = parse_review_result(
        json.dumps(
            {
                "has_issue": True,
                "summary": "错误引用",
                "issues": [
                    {
                        "issue_type": "unnecessary_quote",
                        "severity": "medium",
                        "evidence_message_ids": ["101"],
                        "summary": "连续回复仍引用旧消息",
                        "expected_behavior": "不引用",
                        "suggested_fix": "修发送层引用策略",
                    }
                ],
            },
            ensure_ascii=False,
        )
    )

    assert result.has_issue is True
    assert result.issues[0].issue_type == "unnecessary_quote"
    assert result.issues[0].evidence_message_ids == ("101",)


def test_parse_review_result_treats_non_empty_issues_as_problem() -> None:
    result = parse_review_result(
        json.dumps(
            {
                "has_issue": False,
                "summary": "写了问题但布尔值错误",
                "issues": [
                    {
                        "issue_type": "low_quality_answer",
                        "severity": "medium",
                        "summary": "有明确问题",
                    }
                ],
            },
            ensure_ascii=False,
        )
    )

    assert result.has_issue is True
    assert result.summary == "写了问题但布尔值错误"


def test_build_auto_fix_prompt_requires_tests_and_commit() -> None:
    result = parse_review_result('{"has_issue":true,"summary":"误接话","issues":[]}')

    prompt = build_auto_fix_prompt(result, groups=[], since=100)

    assert "自动修复 qqbot 源码" in prompt
    assert "优先补或更新回归测试" in prompt
    assert "提交一个中文 conventional commit" in prompt
    assert "不要 push" in prompt
    assert "外层会在成功后私聊 Bot 作者简短说明" in prompt


def test_reply_review_service_skips_when_no_bot_messages(tmp_path: Path) -> None:
    executor = FakeExecutor()
    service = AiReplyReviewService(
        settings=RuntimeSettings(data_root=tmp_path / "run"),
        action_executor=executor,  # type: ignore[arg-type]
        gateway_factory=lambda settings, profile: FakeGateway('{"has_issue":false,"summary":"无问题","issues":[]}'),
        now=lambda: 2000,
    )

    assert asyncio.run(service.run_once()) is False
    assert executor.requests == []


def test_reply_review_service_does_not_fix_when_review_says_no_issue(tmp_path: Path) -> None:
    store = GroupMessageLogStore(tmp_path / "run")
    store.append_message(
        group_id=10001,
        direction="bot",
        user_id=30001,
        sender_name="Bot",
        text="正常回复",
        timestamp=1900,
        message_id=12,
    )
    executor = FakeExecutor()
    gateway = FakeGateway('{"has_issue":false,"summary":"无问题","issues":[]}')
    service = AiReplyReviewService(
        settings=RuntimeSettings(data_root=tmp_path / "run"),
        action_executor=executor,  # type: ignore[arg-type]
        gateway_factory=lambda settings, profile: gateway,
        now=lambda: 2000,
    )

    assert asyncio.run(service.run_once()) is False

    assert executor.requests == []
    assert gateway.requests


def test_reply_review_service_starts_codex_and_private_notice_on_issue(tmp_path: Path) -> None:
    store = GroupMessageLogStore(tmp_path / "run")
    store.append_message(
        group_id=10001,
        direction="incoming",
        user_id=20001,
        sender_name="甲",
        text="怎么还是 markdown",
        timestamp=1900,
        message_id=11,
    )
    store.append_message(
        group_id=10001,
        direction="bot",
        user_id=30001,
        sender_name="Bot",
        text="抱歉，我改",
        timestamp=1901,
        message_id=12,
        quote_message_id=11,
        delivery_mode="direct",
    )
    executor = FakeExecutor()
    gateway = FakeGateway(
        json.dumps(
            {
                "has_issue": True,
                "summary": "把别人机器人输出当成自己",
                "issues": [
                    {
                        "issue_type": "wrong_self_reference",
                        "severity": "high",
                        "evidence_message_ids": ["12"],
                        "summary": "不该代替别人道歉",
                        "expected_behavior": "静默",
                        "suggested_fix": "收紧触发",
                    }
                ],
            },
            ensure_ascii=False,
        )
    )
    profile_file = tmp_path / "profiles.toml"
    profile_file.write_text(
        """
[ai.providers.openrouter-icu]
provider = "openai_compatible"
base_url = "https://rehdasu.cn/v1"
model = "gpt-5.5"
api_key_env = "dummy"
enabled = true

[ai.providers.rightcodes]
provider = "openai_compatible"
base_url = "https://right.codes/v1"
model = "gpt-5.5"
api_key_env = "dummy"
enabled = true
""".strip(),
        encoding="utf-8",
    )
    built_profiles = []
    service = AiReplyReviewService(
        settings=RuntimeSettings(data_root=tmp_path / "run", ai_profile_file=profile_file, author_qq=10000),
        action_executor=executor,  # type: ignore[arg-type]
        gateway_factory=lambda settings, profile: built_profiles.append(profile) or gateway,
        now=lambda: 2000,
    )

    assert asyncio.run(service.run_once()) is True

    assert [request.action_type for request in executor.requests] == ["run_codex_task"]
    codex_request = executor.requests[0]
    assert built_profiles == ["openrouter-icu"]
    assert codex_request.actor_user_id == "10000"
    assert codex_request.target_user_id == "10000"
    assert codex_request.codex_project_id == "qqbot"
    assert codex_request.is_admin is True
    assert "把别人机器人输出当成自己" in codex_request.codex_prompt


def test_reply_review_service_falls_back_from_openrouter_icu_to_rightcodes(tmp_path: Path) -> None:
    store = GroupMessageLogStore(tmp_path / "run")
    store.append_message(
        group_id=10001,
        direction="bot",
        user_id=30001,
        sender_name="Bot",
        text="正常回复",
        timestamp=1900,
        message_id=12,
    )
    profile_file = tmp_path / "profiles.toml"
    profile_file.write_text(
        """
[ai.providers.openrouter-icu]
provider = "openai_compatible"
base_url = "https://rehdasu.cn/v1"
model = "gpt-5.5"
api_key_env = "dummy"
enabled = true

[ai.providers.rightcodes]
provider = "openai_compatible"
base_url = "https://right.codes/v1"
model = "gpt-5.5"
api_key_env = "dummy"
enabled = true
""".strip(),
        encoding="utf-8",
    )
    fallback_gateway = FallbackGateway()
    success_gateway = FakeGateway('{"has_issue":false,"summary":"无问题","issues":[]}')
    built_profiles = []

    def gateway_factory(settings, profile):
        built_profiles.append(profile)
        if profile == "openrouter-icu":
            return fallback_gateway
        return success_gateway

    service = AiReplyReviewService(
        settings=RuntimeSettings(data_root=tmp_path / "run", ai_profile_file=profile_file),
        action_executor=FakeExecutor(),  # type: ignore[arg-type]
        gateway_factory=gateway_factory,
        now=lambda: 2000,
    )

    assert asyncio.run(service.run_once()) is False

    assert built_profiles == ["openrouter-icu", "rightcodes"]
    assert fallback_gateway.requests
    assert success_gateway.requests

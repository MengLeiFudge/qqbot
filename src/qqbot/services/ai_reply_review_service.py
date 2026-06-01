from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any

from qqbot.config import RuntimeSettings
from qqbot.services.ai_actions import AiActionExecutor, AiActionRequest
from qqbot.services.ai_gateway import AiRequest, AiResponse
from qqbot.services.ai_profile_registry import load_ai_profiles
from qqbot.services.ai_runtime import (
    build_ai_gateway,
    list_ai_profile_fallback_order,
)
from qqbot.services.group_message_log_store import GroupMessageLogRecord, GroupMessageLogStore
from qqbot.services.json_file_store import atomic_write_json, load_json_array
from qqbot.services.settings_store import SettingsStore


DEFAULT_REVIEW_INTERVAL_SECONDS = 60 * 60
DEFAULT_REVIEW_WINDOW_SECONDS = 60 * 60
REVIEW_STATE_FILE = "ai/reply_review_state.json"
REVIEW_CANDIDATES_FILE = "ai/review_candidates.jsonl"


@dataclass(frozen=True, slots=True)
class AiReplyReviewIssue:
    issue_type: str
    severity: str
    evidence_message_ids: tuple[str, ...]
    summary: str
    expected_behavior: str
    suggested_fix: str


@dataclass(frozen=True, slots=True)
class AiReplyReviewResult:
    has_issue: bool
    summary: str
    issues: tuple[AiReplyReviewIssue, ...] = ()


class AiReplyReviewService:
    def __init__(
        self,
        *,
        settings: RuntimeSettings,
        action_executor: AiActionExecutor,
        review_profile: str = "",
        actor_user_id: str = "",
        now: Callable[[], float] = time.time,
        gateway_factory: Callable[[RuntimeSettings, str], Any] = build_ai_gateway,
    ) -> None:
        self.settings = settings
        self.action_executor = action_executor
        self.review_profile = review_profile
        self.actor_user_id = actor_user_id.strip() or str(settings.author_qq)
        self.now = now
        self.gateway_factory = gateway_factory
        self.data_root = Path(settings.data_root)

    async def run_once(self, *, window_seconds: int = DEFAULT_REVIEW_WINDOW_SECONDS) -> bool:
        state = self._load_state()
        if bool(state.get("running", False)):
            return False
        state["running"] = True
        self._write_state(state)
        try:
            since = int(self.now()) - max(1, int(window_seconds))
            groups = self._collect_review_groups(since)
            if not groups:
                state["last_checked_at"] = int(self.now())
                self._write_state({**state, "running": False})
                return False
            result = await self._review_groups(groups, since=since)
            self._append_review_result(result, groups=groups, since=since)
            state["last_checked_at"] = int(self.now())
            state["last_summary"] = result.summary
            self._write_state({**state, "running": False})
            if not result.has_issue:
                return False
            await self._start_auto_fix(result, groups=groups, since=since)
            return True
        except Exception as exc:
            self._write_state(
                {
                    **state,
                    "running": False,
                    "last_error": f"{type(exc).__name__}: {exc}",
                    "last_checked_at": int(self.now()),
                }
            )
            raise

    def _collect_review_groups(self, since: int) -> list[dict[str, object]]:
        store = GroupMessageLogStore(self.data_root)
        groups: list[dict[str, object]] = []
        for group_id in store.list_group_ids():
            records = tuple(record for record in store.load_messages(group_id) if record.timestamp >= since)
            if not any(record.direction == "bot" for record in records):
                continue
            groups.append(
                {
                    "group_id": str(group_id),
                    "messages": [_record_to_review_payload(record) for record in records[-80:]],
                }
            )
        return groups

    async def _review_groups(
        self,
        groups: list[dict[str, object]],
        *,
        since: int,
    ) -> AiReplyReviewResult:
        last_response: AiResponse | None = None
        for profile_name in self._resolve_review_profiles():
            try:
                gateway = self.gateway_factory(self.settings, profile_name)
            except ValueError:
                continue
            response: AiResponse = await gateway.complete(
                AiRequest(
                    plugin_id="ai",
                    capability="chat",
                    prompt="请审查最近 QQ 群里机器人回复是否存在介入、引用、身份判断或回答质量问题。",
                    user_id=self.actor_user_id,
                    context=(build_review_prompt(groups, since=since),),
                )
            )
            if not response.fallback:
                return parse_review_result(response.text)
            last_response = response
        return AiReplyReviewResult(
            False,
            f"自审失败：{last_response.fallback_reason or last_response.text if last_response else 'no_profile'}",
        )

    async def _start_auto_fix(
        self,
        result: AiReplyReviewResult,
        *,
        groups: list[dict[str, object]],
        since: int,
    ) -> None:
        prompt = build_auto_fix_prompt(result, groups=groups, since=since)
        await self.action_executor.execute(
            AiActionRequest(
                action_type="run_codex_task",
                actor_user_id=self.actor_user_id,
                target_user_id=self.actor_user_id,
                codex_project_id="qqbot",
                codex_prompt=prompt,
                codex_evidence=json.dumps(_review_result_payload(result), ensure_ascii=False, indent=2),
                is_admin=True,
                source="ai_reply_review",
            )
        )

    def _append_review_result(
        self,
        result: AiReplyReviewResult,
        *,
        groups: list[dict[str, object]],
        since: int,
    ) -> None:
        path = self.data_root / REVIEW_CANDIDATES_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at": int(self.now()),
            "since": since,
            "review_profiles": list(self._resolve_review_profiles()),
            "group_count": len(groups),
            "result": _review_result_payload(result),
        }
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _load_state(self) -> dict[str, object]:
        path = self.data_root / REVIEW_STATE_FILE
        if not path.exists():
            return {}
        records = load_json_array(path)
        if records and isinstance(records[-1], dict):
            return dict(records[-1])
        return {}

    def _write_state(self, state: dict[str, object]) -> None:
        atomic_write_json(self.data_root / REVIEW_STATE_FILE, [state])

    def _resolve_review_profiles(self) -> tuple[str, ...]:
        profiles = load_ai_profiles(self.settings.ai_profile_file)
        store = SettingsStore(self.data_root, self.settings.author_qq)
        order = list_ai_profile_fallback_order(
            self.settings,
            store,
            profiles,
            preferred_profile=self.review_profile or None,
        )
        gpt_order = tuple(
            name
            for name in order
            if (profile := profiles.get(name)) is not None
            and profile.enabled
            and profile.model.lower().startswith("gpt-")
        )
        return gpt_order or order


async def run_ai_reply_review_loop(
    *,
    settings: RuntimeSettings,
    action_executor: AiActionExecutor,
    interval_seconds: int = DEFAULT_REVIEW_INTERVAL_SECONDS,
    sleep: Callable[[float], Awaitable[None]],
) -> None:
    service = AiReplyReviewService(settings=settings, action_executor=action_executor)
    while True:
        await service.run_once()
        await sleep(interval_seconds)


def build_review_prompt(groups: list[dict[str, object]], *, since: int) -> str:
    return (
        "你是 QQ 群聊机器人回复质量审查器，使用 gpt-5.5 high 判断。\n"
        "只要你认为机器人回复有问题，就输出 has_issue=true；认为没问题就输出 false。\n"
        "重点检查：不是在说机器人却接话、没有必要却引用、主动介入时机不对、领域问题没查源码、回答质量低、暴露内部机制、身份判断错误、安全过度反应。\n"
        "必须只输出 JSON，不要 Markdown。\n"
        "JSON 格式：{\"has_issue\":bool,\"summary\":\"...\",\"issues\":[{\"issue_type\":\"...\",\"severity\":\"low|medium|high\",\"evidence_message_ids\":[\"...\"],\"summary\":\"...\",\"expected_behavior\":\"...\",\"suggested_fix\":\"...\"}]}\n"
        f"审查窗口起点 timestamp={since}。\n"
        "最近群聊记录：\n"
        f"{json.dumps(groups, ensure_ascii=False)}"
    )


def build_auto_fix_prompt(
    result: AiReplyReviewResult,
    *,
    groups: list[dict[str, object]],
    since: int,
) -> str:
    return (
        "gpt-5.5 high 自审判定 qqbot 的 AI 群聊回复存在问题。请自动修复 qqbot 源码。\n"
        "要求：\n"
        "1. 根据 evidence_message_ids 和上下文定位错误行为。\n"
        "2. 优先补或更新回归测试。\n"
        "3. 运行相关测试；如果影响共享链路，运行全量 pytest。\n"
        "4. 提交一个中文 conventional commit。\n"
        "5. 修改完成后按本仓库规则重启 bot。\n"
        "6. 不要 push。\n"
        "7. 不要主动向 QQ 发送过程消息；外层会在成功后私聊 Bot 作者简短说明改了什么。\n"
        "审查结果：\n"
        f"{json.dumps(_review_result_payload(result), ensure_ascii=False, indent=2)}\n"
        f"审查窗口起点 timestamp={since}。\n"
        "相关群聊记录：\n"
        f"{json.dumps(groups, ensure_ascii=False, indent=2)}"
    )


def parse_review_result(text: str) -> AiReplyReviewResult:
    try:
        payload = json.loads(_extract_json_object(text))
    except json.JSONDecodeError:
        return AiReplyReviewResult(True, f"自审输出不是合法 JSON：{_shorten(text, 160)}")
    issues = tuple(
        AiReplyReviewIssue(
            issue_type=str(item.get("issue_type", "")),
            severity=str(item.get("severity", "")),
            evidence_message_ids=tuple(str(value) for value in item.get("evidence_message_ids", []) if str(value)),
            summary=str(item.get("summary", "")),
            expected_behavior=str(item.get("expected_behavior", "")),
            suggested_fix=str(item.get("suggested_fix", "")),
        )
        for item in payload.get("issues", [])
        if isinstance(item, dict)
    )
    return AiReplyReviewResult(
        has_issue=bool(payload.get("has_issue", False)) or bool(issues),
        summary=str(payload.get("summary", "")).strip() or ("发现问题" if issues else "未发现问题"),
        issues=issues,
    )


def _extract_json_object(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        return cleaned[start : end + 1]
    return cleaned


def _record_to_review_payload(record: GroupMessageLogRecord) -> dict[str, object]:
    return {
        "direction": record.direction,
        "user_id": record.user_id,
        "sender_name": record.sender_name,
        "text": record.text,
        "timestamp": record.timestamp,
        "message_id": record.message_id,
        "quote_message_id": record.quote_message_id,
        "delivery_mode": record.delivery_mode,
    }


def _review_result_payload(result: AiReplyReviewResult) -> dict[str, object]:
    return {
        "has_issue": result.has_issue,
        "summary": result.summary,
        "issues": [
            {
                "issue_type": issue.issue_type,
                "severity": issue.severity,
                "evidence_message_ids": list(issue.evidence_message_ids),
                "summary": issue.summary,
                "expected_behavior": issue.expected_behavior,
                "suggested_fix": issue.suggested_fix,
            }
            for issue in result.issues
        ],
    }


def _shorten(text: str, limit: int) -> str:
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"

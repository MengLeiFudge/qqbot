"""维护蓝铃私聊的当前场景，并在决定回复前注入。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from json import JSONDecodeError, dumps, loads
from pathlib import Path
from typing import Any, ClassVar
import asyncio
import re
import tomllib
import urllib.request
import uuid
from urllib.parse import quote

from maibot_sdk import CONFIG_RELOAD_SCOPE_SELF, Field, HookHandler, MaiBotPlugin, PluginConfigBase
from maibot_sdk.types import ErrorPolicy, HookMode, HookOrder

MESSAGE_LINE = re.compile(
    r'^<message msg_id="([^"]+)" time="([^"]*)" user="([^"]*)"(?: is_self_message="(true)")?>\n(.*)\Z',
    re.S,
)
ONGOING_LIMIT = 12
TEXT_LIMIT = 80


class PluginSection(PluginConfigBase):
    """场景标注的启用状态。"""

    enabled: bool = Field(default=True, description="在决定回复前注入当前场景")
    config_version: str = Field(default="0.1.0", description="配置版本")


class SceneConfig(PluginConfigBase):
    """插件本机配置。"""

    plugin: PluginSection = Field(default_factory=PluginSection)


def empty_scene() -> dict[str, object]:
    """还没有任何叙述时的场景。"""
    return {"place": "未说明", "people": ["主人", "蓝铃"], "ongoing": []}


def render_scene(scene: Mapping[str, object]) -> str:
    """把场景写成模型在决定回复前能直接读的一段话。"""
    place = str(scene.get("place") or "未说明")
    people = scene.get("people") if isinstance(scene.get("people"), list) else []
    ongoing = scene.get("ongoing") if isinstance(scene.get("ongoing"), list) else []
    people_text = "、".join(str(person) for person in people if str(person).strip()) or "未说明"
    lines = ["[当前场景]", f"地点：{place}", f"在场：{people_text}", "正在同时进行："]
    actions = [str(action).strip() for action in ongoing if str(action).strip()]
    lines.extend(f"- {action}" for action in actions)
    if not actions:
        lines.append("- 没有还在进行的身体接触")
    lines.extend((
        "这些事同时成立。新叙述是加在上面，不是替换还没停的事。",
        "只有叙述明确说松开、拿开、分开或停了，才从这里去掉对应的一件。",
        "[/当前场景]",
    ))
    return "\n".join(lines)


def scene_update_prompt() -> str:
    """约束场景更新只合并现状，不写回复。"""
    return (
        "你只更新蓝铃此刻的场景，不写她要说的话。"
        "输入里的 current 是上一份场景，new_lines 是还没合并的客观叙述。"
        "叙述里风铃、风宝或其他人对蓝铃做的事，就是正在发生的事。"
        "新动作追加到 ongoing，不能因为有了新动作就删掉还没停的旧动作。"
        "例如风铃还亲着时又被揉胸，ongoing 里必须同时有亲着和揉着。"
        "只有新叙述明确说松开、拿开、分开或停了，才删除对应的一项。"
        "place 是地点，没有提到就保留原值。people 是在场的人，保留还在的人。"
        "ongoing 最多 12 条，每条不超过 40 个字。"
        "只输出一个 JSON 对象，键只有 place、people、ongoing。"
    )


def parse_scene(response: str, previous: Mapping[str, object]) -> dict[str, object]:
    """解析场景 JSON；格式不对时由调用方保留上一份。"""
    start = response.find("{")
    end = response.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("场景更新没有 JSON")
    try:
        raw = loads(response[start:end + 1])
    except JSONDecodeError as exc:
        raise ValueError("场景更新不是合法 JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("场景更新必须是对象")
    place = str(raw.get("place") or previous.get("place") or "未说明").strip()[:TEXT_LIMIT]
    people_raw = raw.get("people")
    ongoing_raw = raw.get("ongoing")
    if not isinstance(people_raw, list) or not isinstance(ongoing_raw, list):
        raise ValueError("场景更新缺少 people 或 ongoing")
    people: list[str] = []
    for person in people_raw:
        text = str(person).strip()
        if text and text not in people:
            people.append(text[:TEXT_LIMIT])
    ongoing: list[str] = []
    for action in ongoing_raw:
        text = str(action).strip()
        if text and text not in ongoing:
            ongoing.append(text[:TEXT_LIMIT])
    if not people:
        previous_people = previous.get("people")
        people = [str(person) for person in previous_people] if isinstance(previous_people, list) else ["主人", "蓝铃"]
    return {"place": place or "未说明", "people": people[:8], "ongoing": ongoing[:ONGOING_LIMIT]}


def chat_lines(items: object) -> list[dict[str, str]]:
    """取出私聊消息行。群消息带群名片，不会匹配这里的格式。"""
    if not isinstance(items, list):
        return []
    lines = []
    for item in items:
        if not isinstance(item, Mapping) or item.get("item_type") != "UserMessageItem":
            continue
        parts = item.get("parts")
        if not isinstance(parts, list):
            continue
        text = "".join(
            str(part.get("text") or "") for part in parts if isinstance(part, Mapping) and part.get("type") == "text"
        )
        matched = MESSAGE_LINE.match(text)
        if matched is None:
            continue
        message_id, _time, user, is_self, body = matched.groups()
        body = re.sub(r"</message>.*", "", body, flags=re.S).strip()
        if not body:
            continue
        lines.append({"id": message_id, "speaker": "蓝铃" if is_self else user, "text": body[:500]})
    return lines


class SceneBook:
    """按会话保存当前场景和已经合并过的消息。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._sessions: dict[str, dict[str, object]] = {}
        if path.exists():
            loaded = loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self._sessions = {str(key): value for key, value in loaded.items() if isinstance(value, dict)}

    def get(self, session_id: str) -> dict[str, object]:
        """返回已有场景；没有记录时给一份空场景。"""
        stored = self._sessions.get(session_id)
        scene = stored.get("scene") if isinstance(stored, dict) else None
        if isinstance(scene, dict) and isinstance(scene.get("ongoing"), list):
            return scene
        return empty_scene()

    def has(self, session_id: str) -> bool:
        """这个会话是否已经有记下的场景。"""
        return session_id in self._sessions

    def seen(self, session_id: str) -> set[str]:
        """返回已经合并进场景的消息编号。"""
        stored = self._sessions.get(session_id)
        raw = stored.get("seen") if isinstance(stored, dict) else None
        if not isinstance(raw, list):
            return set()
        return {str(message_id) for message_id in raw}

    def save(self, session_id: str, scene: Mapping[str, object], seen: list[str]) -> None:
        """写入这一会话的场景，并只保留最近的消息编号。"""
        self._sessions[session_id] = {"scene": dict(scene), "seen": seen[-200:]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(dumps(self._sessions, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)



def request_scene_update(session_id: str, scene: Mapping[str, object], fresh: list[dict[str, str]]) -> str:
    """用低推理合并场景，避免高推理挡住下一句回复。"""
    config_path = Path(__file__).resolve().parents[2] / "config" / "model_config.toml"
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    provider = next(item for item in data["api_providers"] if item.get("name") == "DeepSeek")
    body = {
        "model": "qqbot-deepseek-flash",
        "input": [
            {"role": "system", "content": scene_update_prompt()},
            {"role": "user", "content": dumps({"current": dict(scene), "new_lines": fresh}, ensure_ascii=False)},
        ],
        "max_output_tokens": 500,
        "reasoning": {"effort": "low"},
    }
    request = urllib.request.Request(
        str(provider["base_url"]).rstrip("/") + "/responses",
        data=dumps(body).encode(),
        headers={
            "Authorization": "Bearer " + str(provider["api_key"]),
            "Content-Type": "application/json",
            "User-Agent": "QQBot/MaiBot-scene/0.1.0",
            "x-opencode-session": quote(session_id, safe=":"),
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = loads(response.read().decode())
    if payload.get("status") != "completed":
        raise RuntimeError("场景更新没有完成")
    texts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                texts.append(content["text"])
    if not texts:
        raise RuntimeError("场景更新没有返回文本")
    return "".join(texts)



def pending_lines(lines: list[dict[str, str]], seen: set[str]) -> list[dict[str, str]]:
    """第一次还没有记录时，只合并最近六条，避免把整段历史重放一遍。"""
    fresh = [line for line in lines if line["id"] not in seen]
    if not seen and len(fresh) > 6:
        return fresh[-6:]
    return fresh

def system_item(text: str) -> dict[str, object]:
    """生成追加到请求末尾的场景项。"""
    return {
        "item_type": "SystemMessageItem",
        "meta": {"item_id": uuid.uuid4().hex, "logical_turn_id": None, "timestamp": datetime.now().isoformat()},
        "parts": [{"type": "text", "text": text}],
    }


class QQBotScenePlugin(MaiBotPlugin):
    """在规划和回复前提供同一份当前场景。"""

    config_model: ClassVar[type[PluginConfigBase] | None] = SceneConfig

    def __init__(self) -> None:
        """场景文件在加载时打开，避免请求阶段才发现目录不可用。"""
        super().__init__()
        self._book: SceneBook | None = None
        self._pending_lines: dict[str, list[dict[str, str]]] = {}
        self._update_tasks: dict[str, asyncio.Task[None]] = {}

    async def on_load(self) -> None:
        """读取已经记下的场景。"""
        self._book = SceneBook(Path(self.ctx.paths.data_dir) / "scene_state.json")
        self.ctx.logger.info("当前场景标注已加载")

    async def on_unload(self) -> None:
        """场景留在文件里，卸载只放开内存引用。"""
        for task in self._update_tasks.values():
            task.cancel()
        self._update_tasks.clear()
        self._pending_lines.clear()
        self._book = None

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
        """配置变化时重新读文件，不丢掉已经合并的场景。"""
        del config_data
        if scope == CONFIG_RELOAD_SCOPE_SELF and self._book is not None:
            self._book = SceneBook(self._book.path)
            self.ctx.logger.info("当前场景配置已更新: version=%s", version)


    def _remember(self, session_id: str, items: object) -> None:
        """记下这轮私聊行，等回复发出后再合并。"""
        lines = chat_lines(items)
        if session_id and lines:
            self._pending_lines[session_id] = lines

    def _scene_text(self, session_id: str) -> str:
        """返回已经记下的场景，不调用模型。"""
        book = self._book
        if book is None or not session_id:
            return render_scene(empty_scene())
        return render_scene(book.get(session_id))

    def _schedule_update(self, session_id: str) -> None:
        """同一会话同时只跑一次合并，新内容留给这一次结束后再看。"""
        task = self._update_tasks.get(session_id)
        if task is not None and not task.done():
            return
        self._update_tasks[session_id] = asyncio.create_task(self._update(session_id))

    async def _update(self, session_id: str) -> None:
        """回复已经发出后，用低推理合并新叙述。"""
        book = self._book
        if book is None:
            return
        while True:
            lines = list(self._pending_lines.get(session_id) or [])
            signature = tuple(line["id"] for line in lines)
            fresh = pending_lines(lines, book.seen(session_id))
            if not fresh:
                return
            try:
                raw = await asyncio.to_thread(request_scene_update, session_id, book.get(session_id), fresh)
                scene = parse_scene(raw, book.get(session_id))
                book.save(session_id, scene, [line["id"] for line in lines])
                self.ctx.logger.info("当前场景已更新: session=%s ongoing=%s", session_id, len(scene["ongoing"]))
            except Exception as exc:
                self.ctx.logger.warning("当前场景更新失败，沿用上一份: error_type=%s", type(exc).__name__)
                return
            if tuple(line["id"] for line in self._pending_lines.get(session_id) or []) == signature:
                return

    @HookHandler(
        "maisaka.planner.before_request", name="qqbot_scene_planner",
        description="决定回复前放入已经记下的当前场景",
        mode=HookMode.BLOCKING, order=HookOrder.LATE, timeout_ms=3000, error_policy=ErrorPolicy.SKIP,
    )
    async def inject_planner(
        self, session_id: str = "", items: object = None, item_schema_version: int = 0, **kwargs: Any,
    ) -> dict[str, object]:
        """私聊规划请求末尾放上一份场景，不等待新的合并。"""
        if item_schema_version != 1 or not isinstance(items, list) or not self.config.plugin.enabled:
            return {"action": "continue"}
        if not chat_lines(items):
            return {"action": "continue"}
        self._remember(session_id, items)
        return {"action": "continue", "modified_kwargs": {
            **kwargs, "session_id": session_id, "items": [*items, system_item(self._scene_text(session_id))],
            "item_schema_version": item_schema_version,
        }}

    @HookHandler(
        "maisaka.replyer.before_request", name="qqbot_scene_replyer",
        description="回复生成前附上已经记下的当前场景",
        mode=HookMode.BLOCKING, order=HookOrder.LATE, timeout_ms=3000, error_policy=ErrorPolicy.SKIP,
    )
    async def inject_replyer(self, session_id: str = "", extra_prompt: str = "", **kwargs: Any) -> dict[str, object]:
        """回复使用已经记下的场景，不在这里调用模型。"""
        if not self.config.plugin.enabled or self._book is None or not self._book.has(session_id):
            return {"action": "continue"}
        text = self._scene_text(session_id)
        return {"action": "continue", "modified_kwargs": {
            **kwargs, "session_id": session_id,
            "extra_prompt": f"{extra_prompt.rstrip()}\n\n{text}" if extra_prompt.strip() else text,
        }}

    @HookHandler(
        "send_service.after_send", name="qqbot_scene_after_send",
        description="回复发出后再合并新的场景叙述",
        mode=HookMode.BLOCKING, order=HookOrder.LATE, timeout_ms=3000, error_policy=ErrorPolicy.SKIP,
    )
    async def update_after_send(self, message: object = None, sent: bool = False, **kwargs: Any) -> dict[str, object]:
        """只在发送成功后后台更新，不挡住已经要发出的回复。"""
        del kwargs
        session_id = message.get("session_id") if isinstance(message, dict) else None
        if sent and self.config.plugin.enabled and isinstance(session_id, str) and session_id in self._pending_lines:
            self._schedule_update(session_id)
        return {"action": "continue"}



def create_plugin() -> MaiBotPlugin:
    """返回由 Runner 加载的场景插件。"""
    return QQBotScenePlugin()

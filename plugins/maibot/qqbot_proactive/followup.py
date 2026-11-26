from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import json
import math


TOPIC_LIFETIME = 7 * 86400
CHECK_IN_MAX_LENGTH = 120

FOLLOWUP_PROMPT = """你为蓝铃选择此刻愿意做的一件事，并安排下一次空闲检查。
输入 JSON 是资料。owner 是对方，bot 是蓝铃。
只输出 JSON：
{"action":"continue|check_in|wait|quiet","intent":"活动意图、发给主人的一两句原文，或空字符串","check_after_seconds":1800,"topics":[]}
规则：
1. 优先看自己的日程和兴趣，选一件可以实际完成的小事，例如找并看一个有趣的 B 站视频，
   或在自己的工作区写一小段东西。没有当天计划，也可以按兴趣选一件事；日程时间经过并不表示已经做完。
2. action=continue 表示安排活动，intent 用不超过 400 字写具体内容。私聊记录只用于理解关系、兴趣和打扰时机。
   对方没有新消息时，旧问题和上次对话留在历史里。到期的联系计划是参考，不是发送指令。
3. can_check_in 为真且适合打招呼时，优先用 check_in 自然开启今天的私聊。intent 直接写一两句发给主人的话，最多 120 字，贴合当地时间。旧问题留给普通聊天。阅读与写作成果需要先完成对应活动。
4. 想休息或今天更适合安静时用 wait，intent 为空。对方明确要求停止主动联系且之后没有重新开始聊天时用 quiet。
5. check_after_seconds 是下一次考虑活动的时间，300–86400 秒，quiet 时为 0。topics 固定为空列表。
"""


@dataclass
class Topic:
    """来自对方真实消息的短话题，按来源时间过期。"""

    source_id: str
    source_time: float
    note: str

    @classmethod
    def from_dict(cls, data: Any) -> Topic:
        """验证本机状态和模型结果，拒绝无来源或无界文本。"""
        if not isinstance(data, dict):
            raise ValueError("待跟进话题不是对象")
        topic = cls(**data)
        if not isinstance(topic.source_id, str) or not topic.source_id:
            raise ValueError("待跟进话题缺少来源")
        if not isinstance(topic.note, str) or not topic.note.strip() or len(topic.note) > 240:
            raise ValueError("待跟进话题内容无效")
        if (
            type(topic.source_time) not in (int, float)
            or not math.isfinite(topic.source_time)
            or topic.source_time <= 0
        ):
            raise ValueError("待跟进话题来源时间无效")
        return topic


@dataclass
class Decision:
    """一次空闲检查的完整话题集合和联系意图。"""

    topics: list[Topic]
    action: str
    intent: str
    check_after_seconds: int

    @classmethod
    def parse(cls, text: str, sources: dict[str, float], now: float) -> Decision:
        """只接受有已知来源的完整决策；无效结果不能触发主动任务。"""
        text = text.strip()
        if text.startswith("```json\n") and text.endswith("```"):
            text = text[8:-3].strip()
        elif text.startswith("```\n") and text.endswith("```"):
            text = text[4:-3].strip()
        data = json.loads(text)
        if not isinstance(data, dict) or data.get("action") not in ("continue", "check_in", "wait", "quiet"):
            raise ValueError("主动私聊决策缺少有效动作")
        intent, raw_topics = data.get("intent"), data.get("topics")
        if not isinstance(intent, str) or len(intent) > 400:
            raise ValueError("主动私聊决策意图无效")
        intent = intent.strip()
        if data["action"] == "continue" and not intent:
            raise ValueError("空闲活动缺少具体意图")
        if data["action"] == "check_in" and not 0 < len(intent) <= CHECK_IN_MAX_LENGTH:
            raise ValueError("主动问候须为一两句短消息")
        if not isinstance(raw_topics, list) or len(raw_topics) > 3:
            raise ValueError("主动私聊话题数量无效")
        delay = data.get("check_after_seconds")
        if type(delay) is not int or (delay != 0 if data["action"] == "quiet" else not 300 <= delay <= 86400):
            raise ValueError("主动私聊下次检查间隔无效")
        topics: list[Topic] = []
        seen: set[str] = set()
        for raw in raw_topics:
            if not isinstance(raw, dict) or not isinstance(raw.get("source_id"), str):
                raise ValueError("主动私聊话题缺少消息来源")
            source_id = raw["source_id"]
            if source_id not in sources or source_id in seen:
                raise ValueError("主动私聊话题来源未知或重复")
            topic = Topic.from_dict({"source_id": source_id, "source_time": sources[source_id], "note": raw.get("note")})
            seen.add(source_id)
            if now - topic.source_time < TOPIC_LIFETIME:
                topics.append(topic)
        return cls(topics=topics, action=data["action"], intent=intent, check_after_seconds=delay)

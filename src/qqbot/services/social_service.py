from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PokeStep:
    delay_ms: int = 0
    message: str | None = None
    poke_target: int | None = None


@dataclass(slots=True)
class PokePlan:
    steps: list[PokeStep] = field(default_factory=list)


def should_auto_approve_request(request_type: str, sub_type: str | None) -> bool:
    if request_type == "friend":
        return True
    if request_type == "group" and sub_type == "invite":
        return True
    return False


def plan_poke_response(self_id: int, user_id: int, target_id: int, roll: int) -> PokePlan:
    plan = PokePlan()
    if user_id == self_id or roll > 25:
        return plan

    # 旧 mirai 行为：戳 bot 时先回一句，再按概率延迟 1s 继续戳；戳别人时小概率立即跟戳一次。
    if target_id == self_id:
        plan.steps.append(PokeStep(message="谁让你戳我的？我戳！"))
        if roll <= 5:
            plan.steps.append(PokeStep(delay_ms=1000, message="我再戳！", poke_target=user_id))
            if roll <= 1:
                plan.steps.append(
                    PokeStep(delay_ms=1000, message="我还戳！", poke_target=user_id)
                )
        return plan

    plan.steps.append(PokeStep(poke_target=target_id))
    return plan

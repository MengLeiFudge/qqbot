from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_tool_registry import (
    AiToolContext,
    AiToolPermissionError,
    AiToolRegistry,
    build_default_ai_tool_registry,
)


def test_default_registry_lists_core_tools() -> None:
    registry = build_default_ai_tool_registry()

    assert {"shapez.render_code", "bot.schedule_private_message", "proposal.create"} <= {
        tool.name for tool in registry.list_tools()
    }


def test_shapez_render_tool_returns_image_path(tmp_path: Path) -> None:
    registry = build_default_ai_tool_registry()

    result = registry.invoke(
        "shapez.render_code",
        {"code": "CrRgSbWy"},
        AiToolContext(data_root=tmp_path, actor_user_id="10001"),
    )

    assert result.ok is True
    assert result.payload["short_code"] == "CrRgSbWy"
    assert Path(str(result.payload["image_path"])).exists()


def test_unknown_tool_is_rejected(tmp_path: Path) -> None:
    registry = AiToolRegistry()

    with pytest.raises(KeyError):
        registry.invoke("missing.tool", {}, AiToolContext(data_root=tmp_path, actor_user_id="10001"))


def test_admin_only_tool_rejects_normal_user(tmp_path: Path) -> None:
    registry = build_default_ai_tool_registry()

    with pytest.raises(AiToolPermissionError):
        registry.invoke(
            "proposal.create",
            {"plugin": "shapez", "summary": "补 chart", "evidence": ["群聊证据"]},
            AiToolContext(data_root=tmp_path, actor_user_id="10001", is_admin=False),
        )

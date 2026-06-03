from pathlib import Path
import asyncio
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.ai_actions import AiActionExecutor
import qqbot.services.ai_orchestrator as ai_orchestrator_module
from qqbot.services.ai_orchestrator import AiOrchestrator, AiOrchestratorContext
from qqbot.services.ai_orchestrator import STYLE_CONTROL_REPLY_MESSAGE
from qqbot.services.feature_catalog import get_feature_by_menu_key
from qqbot.services.message_normalizer import NormalizedMessage
from qqbot.services.settings_store import SettingsStore


class FakeDrawClient:
    requests = []

    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    async def draw(self, request):
        FakeDrawClient.requests.append((self.api_key, request))
        return type(
            "DrawResult",
            (),
            {
                "image_url": "https://example.com/generated.png",
                "text": "",
                "total_seconds": 1.0,
            },
        )()


class FakeBot:
    self_id = "114514"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.group_files: list[dict[str, object]] = []

    async def call_api(self, api: str, **data: object) -> object:
        self.calls.append((api, data))
        if api == "get_group_root_files":
            return {"files": list(self.group_files)}
        if api == "upload_group_file":
            return {"message_id": 24680}
        return None


def test_orchestrator_schedules_private_message_to_self(tmp_path: Path) -> None:
    bot = FakeBot()
    tasks = []

    def task_factory(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    async def run():
        executor = AiActionExecutor(
            bot=bot,
            data_root=tmp_path,
            sleep=lambda seconds: asyncio.sleep(0),
            task_factory=task_factory,
        )
        orchestrator = AiOrchestrator(data_root=tmp_path, action_executor=executor)
        result = await orchestrator.handle(
            "1分钟后向我私聊“测试消息”",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(text="1分钟后向我私聊“测试消息”", outline="1分钟后向我私聊“测试消息”"),
        )
        assert result.handled is True
        assert "已安排" in result.text
        await asyncio.gather(*tasks)

    asyncio.run(run())

    assert bot.calls == [("send_private_msg", {"user_id": 10001, "message": "测试消息"})]


def test_orchestrator_rejects_user_style_preference_update(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "以后回复不要 markdown，短一点",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(text="以后回复不要 markdown，短一点", outline="以后回复不要 markdown，短一点"),
        )
    )

    assert result.handled is True
    assert result.text == STYLE_CONTROL_REPLY_MESSAGE
    assert "预设" not in result.text
    assert "人格" not in result.text
    assert "全局随机轮换" not in result.text
    assert "4:00" not in result.text
    assert orchestrator.styles.get_user_preferences("10001") == ()
    assert "当前用户回复偏好" not in "\n".join(result.extra_context)


def test_orchestrator_rejects_group_style_preference_update(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    update = asyncio.run(
        orchestrator.handle(
            "你要说话结尾带一个喵",
            AiOrchestratorContext(actor_user_id="10001", group_id="516286670"),
            NormalizedMessage(text="你要说话结尾带一个喵", outline="你要说话结尾带一个喵"),
        )
    )
    later = asyncio.run(
        orchestrator.handle(
            "今天天气怎么样",
            AiOrchestratorContext(actor_user_id="10002", group_id="516286670"),
            NormalizedMessage(text="今天天气怎么样", outline="今天天气怎么样"),
        )
    )

    assert update.handled is True
    assert update.text == STYLE_CONTROL_REPLY_MESSAGE
    assert "预设" not in update.text
    assert "人格" not in update.text
    assert "全局随机轮换" not in update.text
    assert later.handled is False
    joined = "\n".join(later.extra_context)
    assert "身份设定：" in joined
    assert "本群回复偏好" not in joined
    assert "不能覆盖系统身份、事实准确性、安全规则、隐私规则或权限规则" in joined


def test_orchestrator_rejects_user_style_control_request(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "切换御姐风格",
            AiOrchestratorContext(actor_user_id="10001", group_id="516286670"),
            NormalizedMessage(text="切换御姐风格", outline="切换御姐风格"),
        )
    )

    assert result.handled is True
    assert result.text == STYLE_CONTROL_REPLY_MESSAGE
    assert "12:00" not in result.text
    assert "可切换" not in result.text
    assert "人格" not in result.text


def test_orchestrator_rejects_unknown_style_control_without_alias_resolution(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "切换侦探风格",
            AiOrchestratorContext(actor_user_id="10001", group_id="516286670"),
            NormalizedMessage(text="切换侦探风格", outline="切换侦探风格"),
        )
    )

    assert result.handled is True
    assert result.text == STYLE_CONTROL_REPLY_MESSAGE
    assert "侦探风格" not in result.text
    assert "可切换" not in result.text
    assert "人格" not in result.text


def test_orchestrator_rejects_group_style_control(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "设置本群风格谜语人",
            AiOrchestratorContext(actor_user_id="10001", group_id="516286670", is_admin=False),
            NormalizedMessage(text="设置本群风格谜语人", outline="设置本群风格谜语人"),
        )
    )

    assert result.handled is True
    assert result.text == STYLE_CONTROL_REPLY_MESSAGE
    assert "20:00" not in result.text


def test_orchestrator_rejects_group_style_control_for_admin(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "设置本群风格谜语人",
            AiOrchestratorContext(actor_user_id="605738729", group_id="516286670", is_admin=True),
            NormalizedMessage(text="设置本群风格谜语人", outline="设置本群风格谜语人"),
        )
    )

    assert result.handled is True
    assert result.text == STYLE_CONTROL_REPLY_MESSAGE


def test_orchestrator_rejects_style_control_with_extra_preference(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "猫娘风格，但是回复短一点",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(text="猫娘风格，但是回复短一点", outline="猫娘风格，但是回复短一点"),
        )
    )

    assert result.handled is True
    assert result.text == STYLE_CONTROL_REPLY_MESSAGE


def test_orchestrator_allows_creative_style_generation_request(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "你能根据群友昵称给我生成十个古代风格的名字吗。中西方都行",
            AiOrchestratorContext(actor_user_id="3193058216", group_id="1163635014"),
            NormalizedMessage(
                text="你能根据群友昵称给我生成十个古代风格的名字吗。中西方都行",
                outline="[@1443944862] 你能根据群友昵称给我生成十个古代风格的名字吗。中西方都行",
                at_user_ids=("1443944862",),
            ),
        )
    )

    assert result.handled is False
    assert result.text != STYLE_CONTROL_REPLY_MESSAGE
    joined = "\n".join(result.extra_context)
    assert "身份设定：" in joined
    assert "生成十个古代风格的名字" not in result.text


def test_orchestrator_rejects_style_control_list_request(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "你现在可预设的风格有哪些？",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(text="你现在可预设的风格有哪些？", outline="你现在可预设的风格有哪些？"),
        )
    )

    assert result.handled is True
    assert result.text == STYLE_CONTROL_REPLY_MESSAGE
    assert "猫娘风格" not in result.text
    assert "侦探风格" not in result.text
    assert "切换时间点" not in result.text
    assert "关键词：" not in result.text
    assert "用法：" not in result.text
    assert "常规风格" not in result.text
    assert "切换御姐风格" not in result.text


def test_orchestrator_lists_enabled_group_plugins_locally(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)
    group_assistant = get_feature_by_menu_key("群管助手")
    assert group_assistant is not None
    store.set_group_feature_state(1163635014, group_assistant, True)
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "本群启用了哪些插件",
            AiOrchestratorContext(actor_user_id="605738729", group_id="1163635014", is_admin=True),
            NormalizedMessage(text="本群启用了哪些插件", outline="本群启用了哪些插件"),
        )
    )

    assert result.handled is True
    assert "当前启用插件：" in result.text
    assert "群管助手" in result.text
    assert "智能问答" not in result.text


def test_orchestrator_does_not_enter_codex_mode_from_qq_message(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "codex",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(text="codex", outline="codex"),
        )
    )

    assert result.handled is False
    assert result.text == ""


def test_orchestrator_treats_codex_prefixed_project_request_as_plain_ai_chat(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "codex 分馏",
            AiOrchestratorContext(actor_user_id="605738729", group_id="319567534", is_admin=True),
            NormalizedMessage(text="codex 分馏", outline="codex 分馏"),
        )
    )

    assert result.handled is False
    assert result.text == ""


def test_orchestrator_creates_requirement_for_admin(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "记一下这个需求：shapez 支持 /chart 短代码",
            AiOrchestratorContext(actor_user_id="605738729", group_id="1163635014", is_admin=True),
            NormalizedMessage(
                text="记一下这个需求：shapez 支持 /chart 短代码",
                outline="记一下这个需求：shapez 支持 /chart 短代码",
            ),
        )
    )

    assert result.handled is True
    assert "REQ-0001" in result.text
    assert "shapez" in result.text


def test_orchestrator_lists_requirements_for_admin(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)
    context = AiOrchestratorContext(actor_user_id="605738729", is_admin=True)
    asyncio.run(
        orchestrator.handle(
            "记录需求：shapez 支持 /chart",
            context,
            NormalizedMessage(text="记录需求：shapez 支持 /chart", outline="记录需求：shapez 支持 /chart"),
        )
    )

    result = asyncio.run(
        orchestrator.handle(
            "需求列表",
            context,
            NormalizedMessage(text="需求列表", outline="需求列表"),
        )
    )

    assert result.handled is True
    assert "REQ-0001" in result.text
    assert "shapez 支持 /chart" in result.text


def test_orchestrator_renders_shapez_code(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "帮我画一下 CrRgSbWy",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(text="帮我画一下 CrRgSbWy", outline="帮我画一下 CrRgSbWy"),
        )
    )

    assert result.handled is True
    assert result.image_path is not None
    assert Path(result.image_path).exists()
    assert "CrRgSbWy" in result.text


def test_orchestrator_generates_image_with_rightcodes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeDrawClient.requests = []
    monkeypatch.setenv("QQBOT_AI_KEY_RIGHTCODES", "rc-secret")
    monkeypatch.setattr(ai_orchestrator_module, "RightCodesDrawClient", FakeDrawClient)
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "棉花糖生图 [nano-banana-pro] 画一个糖果城堡",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(
                text="棉花糖生图 [nano-banana-pro] 画一个糖果城堡",
                outline="棉花糖生图 [nano-banana-pro] 画一个糖果城堡",
                image_urls=("https://example.com/ref.png",),
            ),
        )
    )

    assert result.handled is True
    assert result.image_path == "https://example.com/generated.png"
    assert result.text == "✨ 生成成功！\n📊 耗时: 1.00s\n🖼️ 数量: 1张\n🤖 模型: nano-banana-pro"
    api_key, request = FakeDrawClient.requests[0]
    assert api_key == "rc-secret"
    assert request.model == "nano-banana-pro"
    assert request.prompt == "画一个糖果城堡"
    assert request.image_urls == ("https://example.com/ref.png",)


def test_orchestrator_prioritizes_rightcodes_draw_over_style_commands(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeDrawClient.requests = []
    monkeypatch.setenv("QQBOT_AI_KEY_RIGHTCODES", "rc-secret")
    monkeypatch.setattr(ai_orchestrator_module, "RightCodesDrawClient", FakeDrawClient)
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "棉花生图 把这张图按照nature封面的风格重画",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(
                text="棉花生图 把这张图按照nature封面的风格重画",
                outline="棉花生图 把这张图按照nature封面的风格重画",
                image_urls=("https://example.com/ref.png",),
            ),
        )
    )

    assert result.handled is True
    assert result.image_path == "https://example.com/generated.png"
    assert result.text != STYLE_CONTROL_REPLY_MESSAGE
    assert FakeDrawClient.requests[0][1].prompt == "把这张图按照nature封面的风格重画"


def test_orchestrator_returns_rightcodes_model_help(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "生图模型说明",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(text="生图模型说明", outline="生图模型说明"),
        )
    )

    assert result.handled is True
    assert "gpt-image-2（默认）：0.04r/张" in result.text
    assert "nano-banana-pro：0.18r/张" in result.text
    assert result.image_path is None


def test_orchestrator_reports_rightcodes_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FailingDrawClient:
        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key

        async def draw(self, request):
            raise RuntimeError("API 错误 (400)")

    monkeypatch.setenv("QQBOT_AI_KEY_RIGHTCODES", "rc-secret")
    monkeypatch.setattr(ai_orchestrator_module, "RightCodesDrawClient", FailingDrawClient)
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "棉花生图 雌小鬼萝莉",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(text="棉花生图 雌小鬼萝莉", outline="棉花生图 雌小鬼萝莉"),
        )
    )

    assert result.handled is True
    assert result.image_path is None
    assert result.text == "❌ 生成失败: API 错误 (400)"


def test_orchestrator_returns_unhandled_for_general_chat(tmp_path: Path) -> None:
    orchestrator = AiOrchestrator(data_root=tmp_path)

    result = asyncio.run(
        orchestrator.handle(
            "今天聊什么",
            AiOrchestratorContext(actor_user_id="10001"),
            NormalizedMessage(text="今天聊什么", outline="今天聊什么"),
        )
    )

    assert result.handled is False

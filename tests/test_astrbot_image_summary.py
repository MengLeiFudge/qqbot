from __future__ import annotations

import asyncio
from enum import Enum
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class ComponentType(str, Enum):
    Image = "Image"


class BaseMessageComponent:
    type: ComponentType

    def __init__(self, **kwargs) -> None:
        self.type = type(self).type
        for key, value in kwargs.items():
            setattr(self, key, value)


class Image(BaseMessageComponent):
    type = ComponentType.Image

    def __init__(self, file: str, **kwargs) -> None:
        super().__init__(file=file, **kwargs)

    async def convert_to_base64(self) -> str:
        return "encoded-image"


components_stub = types.ModuleType("astrbot.api.message_components")
components_stub.BaseMessageComponent = BaseMessageComponent
components_stub.ComponentType = ComponentType
components_stub.Image = Image

astrbot_stub = types.ModuleType("astrbot")
astrbot_api_stub = types.ModuleType("astrbot.api")

module_path = ROOT / "plugins" / "astrbot_plugin_qqbot_features" / "image_summary.py"
spec = importlib.util.spec_from_file_location("qqbot_image_summary_test_module", module_path)
assert spec is not None and spec.loader is not None
image_summary = importlib.util.module_from_spec(spec)
with patch.dict(
    sys.modules,
    {
        "astrbot": astrbot_stub,
        "astrbot.api": astrbot_api_stub,
        "astrbot.api.message_components": components_stub,
    },
):
    spec.loader.exec_module(image_summary)


class StubMessageChain:
    def __init__(self, chain: list[object]) -> None:
        self.chain = chain
        self.type = "test"

    def derive(self, chain: list[object]) -> "StubMessageChain":
        derived = StubMessageChain(chain)
        derived.type = self.type
        return derived


class AstrBotImageSummaryTest(unittest.TestCase):
    def test_pool_contains_all_confirmed_mixed_phrases(self) -> None:
        self.assertEqual(
            image_summary.IMAGE_SUMMARY_POOL,
            (
                "我爱你",
                "今天也很喜欢你",
                "有一点点想你",
                "你超~~可爱！",
                "给你一颗糖",
                "抱一下再看",
                "只给你偷偷看",
                "请签收今日份可爱",
                "我什么都没发",
                "不许装作没看见",
                "被你发现啦",
                "点开会变可爱",
                "看完不许笑我",
                "嗯？你看到了",
                "这次真的不是广告",
                "图片正在看着你",
                "猜猜里面是什么",
                "嘘，偷偷看",
                "这是一个小秘密",
                "别眨眼",
                "有东西掉出来了",
                "前方糖分超标",
                "点开就知道啦",
                "我先藏在这里",
                "给你看个好东西",
                "图片来啦",
                "新鲜出炉",
                "这张有点厉害",
                "一小份快乐",
                "棉花糖掉落了",
                "快收下",
                "好东西要一起看",
            ),
        )
        self.assertEqual(len(set(image_summary.IMAGE_SUMMARY_POOL)), 32)

    def test_local_image_uses_random_summary_and_keeps_standard_image_type(self) -> None:
        with patch.object(image_summary.random, "choice", return_value="嘘，偷偷看"):
            component = image_summary.random_summary_image_from_file("preview.png")

        self.assertIsInstance(component, Image)
        self.assertEqual(component.summary, "嘘，偷偷看")
        self.assertTrue(component.file.startswith("file://"))

    def test_remote_image_uses_random_summary_and_rejects_non_http_url(self) -> None:
        with patch.object(image_summary.random, "choice", return_value="图片来啦"):
            component = image_summary.random_summary_image_from_url(
                "https://example.invalid/preview.png"
            )

        self.assertEqual(component.file, "https://example.invalid/preview.png")
        self.assertEqual(component.summary, "图片来啦")
        with self.assertRaises(ValueError):
            image_summary.random_summary_image_from_url("file:///preview.png")

    def test_onebot_chain_serializes_summary_in_image_data(self) -> None:
        component = image_summary.RandomSummaryImage(
            file="https://example.invalid/image.png",
            summary="给你一颗糖",
        )
        original = StubMessageChain([object(), component])

        converted = asyncio.run(
            image_summary.prepare_onebot_image_summary_chain(original)
        )

        self.assertIsNot(converted, original)
        self.assertEqual(converted.type, "test")
        payload = converted.chain[1].toDict()
        self.assertEqual(
            payload,
            {
                "type": "image",
                "data": {
                    "file": "base64://encoded-image",
                    "summary": "给你一颗糖",
                },
            },
        )

    def test_plain_image_chain_is_not_rebuilt(self) -> None:
        original = StubMessageChain([Image(file="https://example.invalid/plain.png")])

        converted = asyncio.run(
            image_summary.prepare_onebot_image_summary_chain(original)
        )

        self.assertIs(converted, original)


if __name__ == "__main__":
    unittest.main()

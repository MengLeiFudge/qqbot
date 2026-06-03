from unittest.mock import AsyncMock

import pytest

import astrbot.core.message.components as Comp
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


def test_poke_to_dict_matches_onebot_v11_segment_format():
    poke = Comp.Poke(type="126", id=2003)
    assert poke.toDict() == {
        "type": "poke",
        "data": {"type": "126", "id": "2003"},
    }


@pytest.mark.asyncio
async def test_respond_stage_treats_poke_with_target_as_non_empty():
    stage = RespondStage()
    chain = [Comp.Poke(type="126", id=2003)]
    assert await stage._is_empty_message_chain(chain) is False


@pytest.mark.asyncio
async def test_aiocqhttp_parse_json_outputs_standard_poke_data():
    chain = MessageChain([Comp.Poke(type="126", id=2003)])
    data = await AiocqhttpMessageEvent._parse_onebot_json(chain)
    assert data == [{"type": "poke", "data": {"type": "126", "id": "2003"}}]


@pytest.mark.asyncio
async def test_aiocqhttp_parse_json_collapses_plain_blank_lines():
    chain = MessageChain([Comp.Plain("第一句\n\n  \n第二句\r\n\r\n第三句")])
    data = await AiocqhttpMessageEvent._parse_onebot_json(chain)
    assert data == [{"type": "text", "data": {"text": "第一句\n第二句"}}]


@pytest.mark.asyncio
async def test_aiocqhttp_parse_json_keeps_plain_reply_short():
    chain = MessageChain(
        [
            Comp.Plain(
                "大概要准备：\n"
                "QQ 小号\n"
                "NapCat/协议端\n"
                "AstrBot 或其他框架\n"
                "重点是别让它复读，不然群里会升级成猫鱼混战。",
            ),
        ],
    )

    data = await AiocqhttpMessageEvent._parse_onebot_json(chain)

    assert data == [
        {
            "type": "text",
            "data": {"text": "重点是别让它复读，不然群里会升级成猫鱼混战。"},
        },
    ]


@pytest.mark.asyncio
async def test_aiocqhttp_parse_json_limits_plain_reply_to_forty_chars():
    chain = MessageChain(
        [
            Comp.Plain(
                "这个思路挺香：把复杂连线搬到 RV 软件层，shapeU 只当执行平台喵。"
                "优点是接线少、逻辑清晰、好调试；缺点是性能和指令映射要算清楚。",
            ),
        ],
    )

    data = await AiocqhttpMessageEvent._parse_onebot_json(chain)

    text = data[0]["data"]["text"]
    assert len(text) <= 40
    assert text == "这个思路挺香：把复杂连线搬到 RV 软件层，shapeU 只当执行平台喵。"


@pytest.mark.asyncio
async def test_aiocqhttp_send_message_dispatches_onebot_v11_poke_payload():
    bot = AsyncMock()
    chain = MessageChain([Comp.Poke(type="126", id=2003)])

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=chain,
        event=None,
        is_group=True,
        session_id="123456",
    )

    bot.send_group_msg.assert_awaited_once_with(
        group_id=123456,
        message=[{"type": "poke", "data": {"type": "126", "id": "2003"}}],
    )

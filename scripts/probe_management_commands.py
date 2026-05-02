from __future__ import annotations

import asyncio
import json

import websockets


async def exchange(event: dict[str, object]) -> str:
    uri = "ws://127.0.0.1:8080/onebot/v11/ws"
    headers = {
        "X-Self-ID": "123456",
        "X-Client-Role": "Universal",
    }
    async with websockets.connect(uri, additional_headers=headers) as websocket:
        await websocket.send(json.dumps(event, ensure_ascii=False))
        return await asyncio.wait_for(websocket.recv(), timeout=5)


async def main() -> None:
    menu_event = {
        "time": 1712937600,
        "self_id": 123456,
        "post_type": "message",
        "message_type": "group",
        "sub_type": "normal",
        "message_id": 100,
        "group_id": 516286670,
        "user_id": 605738729,
        "message": [{"type": "text", "data": {"text": "菜单"}}],
        "raw_message": "菜单",
        "font": 0,
        "sender": {
            "user_id": 605738729,
            "nickname": "author",
            "sex": "unknown",
            "age": 0,
        },
    }
    print(await exchange(menu_event))


if __name__ == "__main__":
    asyncio.run(main())

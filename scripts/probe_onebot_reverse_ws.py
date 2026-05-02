from __future__ import annotations

import asyncio
import json

import websockets


async def main() -> None:
    uri = "ws://127.0.0.1:8080/onebot/v11/ws"
    headers = {
        "X-Self-ID": "123456",
        "X-Client-Role": "Universal",
    }
    async with websockets.connect(uri, additional_headers=headers) as websocket:
        event = {
            "time": 1712937600,
            "self_id": 123456,
            "post_type": "message",
            "message_type": "private",
            "sub_type": "friend",
            "message_id": 1,
            "user_id": 10001,
            "message": "/ping",
            "raw_message": "/ping",
            "font": 0,
            "sender": {
                "user_id": 10001,
                "nickname": "probe",
                "sex": "unknown",
                "age": 0,
            },
        }
        await websocket.send(json.dumps(event, ensure_ascii=False))
        reply = await asyncio.wait_for(websocket.recv(), timeout=5)
        print(reply)


if __name__ == "__main__":
    asyncio.run(main())

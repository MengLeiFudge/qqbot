from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from astrbot_plugin_qqbot_features.reread_state import RereadRepeatState


class AlwaysRepeatRng:
    def random(self) -> float:
        return 0.0


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class AstrBotRereadStateTest(unittest.TestCase):
    def test_dual_platform_duplicate_event_does_not_count_as_second_repeat(self) -> None:
        clock = Clock()
        state = RereadRepeatState(rng=AlwaysRepeatRng(), now_func=clock)

        self.assertFalse(state.observe("746497406", "把你朋友送我", sender_id="1798140670"))
        clock.now = 1.0
        self.assertFalse(state.observe("746497406", "把你朋友送我", sender_id="1798140670"))
        clock.now = 2.0
        self.assertTrue(state.observe("746497406", "把你朋友送我", sender_id="1908401664"))

    def test_same_sender_can_repeat_after_duplicate_window(self) -> None:
        clock = Clock()
        state = RereadRepeatState(rng=AlwaysRepeatRng(), now_func=clock)

        self.assertFalse(state.observe("746497406", "把你朋友送我", sender_id="1798140670"))
        clock.now = 4.0

        self.assertTrue(state.observe("746497406", "把你朋友送我", sender_id="1798140670"))

    def test_same_message_id_is_still_deduplicated(self) -> None:
        clock = Clock()
        state = RereadRepeatState(rng=AlwaysRepeatRng(), now_func=clock)

        self.assertFalse(state.observe("746497406", "把你朋友送我", message_id="m1", sender_id="1798140670"))
        clock.now = 4.0

        self.assertFalse(state.observe("746497406", "把你朋友送我", message_id="m1", sender_id="1798140670"))


if __name__ == "__main__":
    unittest.main()

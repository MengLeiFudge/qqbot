"""用隔离 QQ 发送出口核对蓝铃的原生首段和后续自然段。"""
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

import src

if (Path(src.__file__).resolve().parents[1] / '.qqbot-release.json').exists():
    raise RuntimeError('请在独立临时目录运行分段检查，使用新配置和空数据库。')


from maibot_sdk.context import PluginContext

from qqbot_reply_guard.plugin import QQBotReplyGuardPlugin
from qqbot_reply_guard.reply_split import split_reply
from qqbot_reply_timing import plugin as timing
from src.chat.message_receive.message import SessionMessage
from src.chat.utils import utils as chat_utils
from src.common.data_models.mai_message_data_model import MessageInfo, UserInfo
from src.common.data_models.message_component_data_model import AtComponent, MessageSequence, TextComponent
from src.common.data_models.reply_generation_data_models import ReplyGenerationResult
from src.core.tooling import ToolInvocation
from src.maisaka.builtin_tool import reply
from src.maisaka.builtin_tool.context import BuiltinToolRuntimeContext
from src.platform_io.drivers.base import PlatformIODriver
from src.platform_io.manager import PlatformIOManager
from src.platform_io.types import DeliveryReceipt, DeliveryStatus, DriverDescriptor, DriverKind, RouteBinding, RouteKey
from src.plugin_runtime.host.hook_dispatcher import HookDispatchResult
from src.services import send_service


class ShortReplyTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.account = '3600812036'
        self.scope = 'lanling'
        self.session_id = 'isolated-session'
        self.clock = 100.0
        self.waits = []
        self.deliveries = []
        self.fail_at = 0
        self.stored = {}
        self.history = []
        self.text = '先确认文件能打开，中文 API Key 中文照常保留。\n\n接下来补上核对结果和操作步骤。'
        self.guard = QQBotReplyGuardPlugin()
        self.timer = timing.QQBotReplyTimingPlugin()
        for plugin, name in ((self.guard, 'mlj.qqbot-reply-guard'), (self.timer, 'mlj.qqbot-reply-timing')):
            plugin.set_plugin_config({'plugin': {'enabled': True, 'config_version': '0.1.0'}})
            plugin._set_context(PluginContext(name, self.rpc))
            await plugin.on_load()
            self.addAsyncCleanup(plugin.on_unload)
        self.source = SessionMessage(message_id='source-1', platform='qq', timestamp=datetime.now())
        self.source.session_id = self.session_id
        self.source.raw_message = MessageSequence([TextComponent('隔离消息')])
        self.source.message_info = MessageInfo(user_info=UserInfo(user_id='123456789', user_nickname='隔离用户'))
        stream = SimpleNamespace(session_id=self.session_id, platform='qq', account_id=self.account,
                                 user_id='123456789', group_id='', group_name='', context=None)
        runtime = SimpleNamespace(session_id=self.session_id, chat_stream=stream, _chat_history=[],
                                  log_prefix='[隔离验证]', find_source_message_by_id=lambda _: self.source,
                                  _update_stage_status=lambda *args: None)
        self.context = BuiltinToolRuntimeContext(None, runtime)
        broker = PlatformIOManager()
        owner = self

        class CaptureDriver(PlatformIODriver):
            async def start(self):
                pass

            async def stop(self):
                pass

            async def send_message(self, message, route_key, metadata=None):
                owner.deliveries.append((message, route_key))
                index = len(owner.deliveries)
                return DeliveryReceipt(
                    internal_message_id=message.message_id, external_message_id=f'qq-{index}', route_key=route_key,
                    status=DeliveryStatus.FAILED if owner.fail_at == index else DeliveryStatus.SENT,
                    driver_id=self.driver_id, driver_kind=DriverKind.PLUGIN,
                )

        driver = CaptureDriver(DriverDescriptor(driver_id='isolated-napcat', kind=DriverKind.PLUGIN,
                                                platform='qq', account_id=self.account, scope=self.scope))
        broker.register_driver(driver)
        broker.bind_send_route(RouteBinding(route_key=RouteKey('qq', self.account, self.scope),
                                            driver_id=driver.driver_id, driver_kind=DriverKind.PLUGIN))
        stack = ExitStack()
        self.addCleanup(stack.close)
        for obj, key, value in (
            (timing, 'time', SimpleNamespace(monotonic=lambda: self.clock)),
            (timing, 'asyncio', SimpleNamespace(sleep=self.sleep)),
            (send_service, 'asyncio', SimpleNamespace(sleep=self.sleep)),
            (send_service, '_get_runtime_manager', lambda: self),
            (self.context, 'get_runtime_manager', lambda: self),
            (send_service, '_chat_manager', SimpleNamespace(get_session_by_session_id=lambda _: stream)),
            (send_service, 'get_platform_io_manager', lambda: broker),
            (broker, 'ensure_send_pipeline_ready', AsyncMock()),
            (send_service, '_store_sent_message', self.store),
            (send_service, '_notify_memory_automation_on_message_sent', AsyncMock()),
            (send_service, '_sync_sent_message_to_maisaka_history', self.sync_history),
            (send_service, '_record_sent_emoji_usage', Mock()),
            (send_service, '_dispatch_adapter_callbacks', AsyncMock()),
            (reply.replyer_manager, 'get_replyer', lambda **kwargs: SimpleNamespace(generate_reply_with_context=self.generate)),
            (send_service.global_config.response_post_process, 'typing_speed', 0.2),
            (chat_utils.global_config.response_post_process, 'enable_response_post_process', True),
            (chat_utils.global_config.response_splitter, 'enable', True),
            (reply.config_module.global_config.experimental, 'enable_rich_reply', False),
        ):
            stack.enter_context(patch.object(obj, key, value))
        await self.timer.receive(message={'platform': 'qq', 'session_id': self.session_id, 'message_id': 'source-1'})
        await self.timer.prepare(session_id=self.session_id, item_schema_version=1, reply_message_id='source-1', items=[])
        self.clock += 0.1

    async def rpc(self, method, plugin_id, payload, **kwargs):
        cap, args = payload['capability'], payload['args']
        if cap == 'config.get':
            values = {'response_post_process.typing_speed': 0.2, 'bot.qq_account': self.account}
            return {'success': True, 'value': values[args['key']]}
        if cap == 'config.get_plugin':
            return {'success': True, 'value': {'napcat_server': {'connection_id': self.scope}}}
        if cap == 'message.get_by_id':
            mid = args['message_id']
            saved = self.source if mid == self.source.message_id else self.stored.get(mid)
            message = {'platform': saved.platform, 'session_id': saved.session_id, 'message_id': mid} if saved else None
            return {'success': True, 'message': message}
        if cap == 'send.text':
            from src.plugin_runtime.capabilities.core import RuntimeCoreCapabilityMixin
            result = await RuntimeCoreCapabilityMixin._cap_send_text(self, plugin_id, cap, args)
            return {'success': True, 'value': result, **result}
        if cap == 'api.call':
            return {'success': True, 'value': {'stale': True, 'queued': True}}
        raise AssertionError(cap)

    @staticmethod
    def _build_send_result(args, message=None, **kwargs):
        return {'sent': message is not None, 'message_id': message.message_id if message else None}

    async def sleep(self, seconds):
        self.waits.append(seconds)
        self.clock += seconds

    async def store(self, message):
        self.stored[message.message_id] = message

    def sync_history(self, message, **kwargs):
        self.history.append(message.processed_plain_text)

    async def invoke_hook(self, name, **kwargs):
        handlers = {
            'maisaka.reply.before_post_process': [self.guard.prepare_reply_breaks],
            'send_service.after_build_message': [self.guard.bind_first_segment, self.timer.prepare_segment],
            'send_service.before_send': [self.timer.prepare_route, self.timer.before_send],
            'send_service.after_send': [self.timer.after_send, self.guard.send_reply_tails],
        }.get(name, [])
        for handler in handlers:
            result = await handler(**kwargs)
            if result.get('action') == 'abort':
                return HookDispatchResult(name, kwargs, aborted=True)
            kwargs.update(result.get('modified_kwargs', {}))
        return HookDispatchResult(name, kwargs)

    async def generate(self, **kwargs):
        result = ReplyGenerationResult(success=True)
        result.completion.response_text = self.text
        return True, result

    async def send_reply(self, **arguments):
        result = await reply.handle_tool(self.context, ToolInvocation(tool_name='reply', call_id='isolated-call',
            arguments={'msg_id': 'source-1', 'set_quote': False, **arguments}))
        task = self.guard._segment_tasks.get(self.session_id)
        if task is not None:
            await task
        return result

    async def test_first_native_then_tail_with_original_route_timing_and_receipt_ids(self):
        with patch.object(chat_utils, 'split_into_sentences_w_remove_punctuation',
                          side_effect=AssertionError('原生分段被调用')):
            result = await self.send_reply(set_quote=True)
        expected = self.text.split('\n\n')
        self.assertTrue(result.success, result.error_message)
        self.assertEqual(result.structured_content['reply_segments'], expected[:1])
        self.assertEqual([
            ''.join(part.text for part in msg.raw_message.components if isinstance(part, TextComponent))
            for msg, _ in self.deliveries
        ], expected)
        self.assertTrue(all(route == RouteKey('qq', self.account, self.scope) for _, route in self.deliveries))
        self.assertEqual(list(self.stored), ['qq-1', 'qq-2'])
        self.assertEqual(self.history, [f'[回复消息] {expected[0]}', expected[1]])
        self.assertTrue(self.deliveries[0][0].reply_to)
        self.assertIsNone(self.deliveries[1][0].reply_to)
        self.assertEqual(len(self.waits), 2)
        self.assertAlmostEqual(self.waits[0], timing.normal_delay(expected[0], 0.2) - 0.1)
        self.assertAlmostEqual(self.waits[1], timing.normal_delay(expected[1], 0.2))

    async def test_short_and_attachment_reply_keep_their_whole_content(self):
        self.text = '中文 API Key 中文，数值 3.5 kg。'
        result = await self.send_reply()
        self.assertTrue(result.success)
        self.assertEqual([msg.processed_plain_text for msg, _ in self.deliveries], [self.text])
        self.deliveries.clear()
        self.text = '这是一段包含必要说明的文字。\n\n下面是完整的下一段和附件说明。'
        with patch.object(reply.config_module.global_config.experimental, 'enable_rich_reply', True):
            result = await self.send_reply(attach_at=[{'user_id': '123456789'}])
        self.assertTrue(result.success)
        self.assertEqual(len(self.deliveries), 1)
        self.assertTrue(any(isinstance(part, AtComponent) for part in self.deliveries[0][0].raw_message.components))

    async def test_first_failure_suppresses_tails(self):
        self.fail_at = 1
        result = await self.send_reply()
        self.assertFalse(result.success)
        self.assertEqual(len(self.deliveries), 1)
        self.assertEqual(self.stored, {})

    async def test_later_failure_stops_remaining_segments(self):
        self.text = '\n\n'.join(['第一段完整说明足够长，先把事情说清楚。', '第二段提供一份足够具体的补充材料。', '第三段接着说剩下需要处理的细节。'])
        self.fail_at = 2
        result = await self.send_reply()
        self.assertTrue(result.success)
        self.assertEqual(len(self.deliveries), 2)
        self.assertEqual(list(self.stored), ['qq-1'])

    def test_natural_segments_preserve_punctuation_and_structure(self):
        first = '请先检查中文 API Key 中文和 3.5 kg 的显示格式。'
        second = '排除问题以后，再照原顺序检查后面的步骤。'
        self.assertEqual(split_reply(first + second), (first, second))
        document = '先按这个命令查看结果。\n\n```text\nfoo bar\n```\n\n接下来核对完整的输出。'
        self.assertEqual(split_reply(document), (document,))
        text = '\n\n'.join(f'第{i}段内容包含足够的信息和清晰的句末标点。' for i in range(5))
        segments = split_reply(text)
        self.assertEqual(len(segments), 3)
        self.assertEqual('\n\n'.join(segments), text)

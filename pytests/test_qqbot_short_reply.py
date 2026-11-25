"""用隔离 QQ 发送出口核对普通回复和后续自然段。"""
from asyncio import timeout
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

from qqbot_reply_timing import plugin as timing
from qqbot_reply_timing.reply_split import split_reply
from src.chat.message_receive.message import SessionMessage
from src.chat.utils import utils as chat_utils
from src.common.data_models.mai_message_data_model import MessageInfo, UserInfo
from src.common.data_models.message_component_data_model import AtComponent, MessageSequence, ReplyComponent, TextComponent
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
        self.account = '1443944862'
        self.scope = 'yunqi'
        self.session_id = 'isolated-session'
        self.clock = 100.0
        self.wall_clock = 1_800_000_000.0
        self.new_messages = 0
        self.count_queries = []
        self.waits = []
        self.deliveries = []
        self.fail_at = 0
        self.stored = {}
        self.history = []
        self.text = (
            '先确认文件能打开，中文 API Key 中文照常保留。也核对一下不同设备的显示结果，看看文件大小和数字是否一致。'
            '\n\n接下来补上核对结果和操作步骤，把需要改的文件列出来。最后再按原来的顺序逐项检查，确保需要保留的内容都在。'
        )
        self.timer = timing.QQBotReplyTimingPlugin()
        self.timer.set_plugin_config({'plugin': {'enabled': True, 'config_version': '0.1.0'}})
        self.timer._set_context(PluginContext('mlj.qqbot-reply-timing', self.rpc))
        await self.timer.on_load()
        self.addAsyncCleanup(self.timer.on_unload)
        self.source = SessionMessage(message_id='source-1', platform='qq', timestamp=datetime.fromtimestamp(self.wall_clock))
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
            (timing, 'time', SimpleNamespace(monotonic=lambda: self.clock, time=lambda: self.wall_clock)),
            (timing, 'asyncio', SimpleNamespace(sleep=self.sleep, timeout=timeout)),
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
            message = {
                'platform': saved.platform, 'session_id': saved.session_id, 'message_id': mid,
                'timestamp': str(saved.timestamp.timestamp()),
            } if saved else None
            return {'success': True, 'message': message}
        if cap == 'message.count_new':
            self.count_queries.append((args['chat_id'], float(args['since'])))
            return {'success': True, 'count': self.new_messages}
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
        self.wall_clock += seconds

    async def store(self, message):
        self.stored[message.message_id] = message

    def sync_history(self, message, **kwargs):
        self.history.append(message.processed_plain_text)

    async def invoke_hook(self, name, **kwargs):
        handlers = {
            'maisaka.reply.before_post_process': [self.timer.prepare_reply_breaks],
            'send_service.after_build_message': [self.timer.prepare_segment],
            'send_service.before_send': [self.timer.prepare_route, self.timer.before_send],
            'send_service.after_send': [self.timer.after_send],
        }.get(name, [])
        for handler in handlers:
            result = await handler(**kwargs)
            if result.get('action') == 'abort':
                return HookDispatchResult(name, kwargs, aborted=True)
            kwargs = result.get('modified_kwargs', kwargs)
        return HookDispatchResult(name, kwargs)

    async def generate(self, **kwargs):
        result = ReplyGenerationResult(success=True)
        result.completion.response_text = self.text
        return True, result

    async def send_reply(self, **arguments):
        result = await reply.handle_tool(self.context, ToolInvocation(tool_name='reply', call_id='isolated-call',
            arguments={'msg_id': 'source-1', 'set_quote': False, **arguments}))
        task = self.timer._segment_tasks.get(self.session_id)
        if task is not None:
            await task
        return result

    async def test_first_native_then_tail_with_original_route_timing_and_receipt_ids(self):
        self.source.timestamp = datetime.fromtimestamp(self.wall_clock - 30)
        self.new_messages = 6
        with patch.object(chat_utils, 'split_into_sentences_w_remove_punctuation',
                          side_effect=AssertionError('原生分段被调用')):
            result = await self.send_reply()
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
        self.assertEqual([
            [part.target_message_id for part in msg.raw_message.components if isinstance(part, ReplyComponent)]
            for msg, _ in self.deliveries
        ], [['source-1'], []])
        self.assertEqual(self.count_queries, [(self.session_id, self.source.timestamp.timestamp())])
        self.assertEqual(len(self.waits), 2)
        self.assertAlmostEqual(self.waits[0], timing.normal_delay(expected[0], 0.2) - 0.1)
        self.assertAlmostEqual(self.waits[1], timing.normal_delay(expected[1], 0.2))

    async def test_five_new_messages_keep_old_reply_unquoted(self):
        self.source.timestamp = datetime.fromtimestamp(self.wall_clock - 90)
        self.new_messages = 5
        result = await self.send_reply(set_quote=True)
        self.assertTrue(result.success, result.error_message)
        self.assertEqual(self.history, self.text.split('\n\n'))
        self.assertEqual(self.count_queries, [(self.session_id, self.source.timestamp.timestamp())])

    async def test_reply_younger_than_thirty_seconds_skips_count_and_quote(self):
        self.source.timestamp = datetime.fromtimestamp(self.wall_clock - 10)
        self.new_messages = 12
        result = await self.send_reply(set_quote=True)
        self.assertTrue(result.success, result.error_message)
        self.assertEqual(self.history, self.text.split('\n\n'))
        self.assertEqual(self.count_queries, [])

    async def test_thirty_seconds_can_elapse_during_first_segment_wait(self):
        self.source.timestamp = datetime.fromtimestamp(self.wall_clock - 29.9)
        self.new_messages = 6
        result = await self.send_reply()
        self.assertTrue(result.success, result.error_message)
        self.assertTrue(any(isinstance(part, ReplyComponent) for part in self.deliveries[0][0].raw_message.components))
        self.assertEqual(self.count_queries, [(self.session_id, self.source.timestamp.timestamp())])

    async def test_short_sentence_with_commas_is_sent_as_one_message(self):
        self.text = '刚记清楚氢氖碳氩，结果又多了几个新名字，背元素周期表都没这么累。'
        result = await self.send_reply()
        self.assertTrue(result.success)
        self.assertEqual([msg.processed_plain_text for msg, _ in self.deliveries], [self.text])

    async def test_short_paragraphs_are_sent_in_the_same_message(self):
        self.text = '文件已经核对。\n\n我晚点再发操作步骤。'
        result = await self.send_reply()
        self.assertTrue(result.success)
        self.assertEqual([msg.processed_plain_text for msg, _ in self.deliveries], [self.text])

    async def test_short_and_attachment_reply_keep_their_whole_content(self):
        self.text = '中文 API Key 中文，数值 3.5 kg。'
        result = await self.send_reply()
        self.assertTrue(result.success)
        self.assertEqual([msg.processed_plain_text for msg, _ in self.deliveries], [self.text])
        self.deliveries.clear()
        self.text = '这是一段包含附件完整说明的文字，先把需要核对的内容和实际会发生的变化集中说明。\n\n下面补上完整的处理步骤和使用范围，接着再标明哪些日期与数字需要回到原始文件核对。'
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
        self.text = '\n\n'.join(
            f'第{i}段包含需要检查的步骤和具体注意事项，可以逐项确认结果并回到原始文件核对其中的日期和数字。'
            for i in range(3)
        )
        self.fail_at = 2
        result = await self.send_reply()
        self.assertTrue(result.success)
        self.assertEqual(len(self.deliveries), 2)
        self.assertEqual(list(self.stored), ['qq-1'])

    def test_natural_segments_preserve_punctuation_and_structure(self):
        first, second = self.text.split('\n\n')
        self.assertEqual(split_reply(first + second), (first, second))
        document = first + '\n\n```text\nfoo bar\n```\n\n' + second
        self.assertEqual(split_reply(document), (document,))
        text = '\n\n'.join(f'第{i}段要核对内容。' + first for i in range(5))
        segments = split_reply(text)
        self.assertEqual(len(segments), 3)
        self.assertEqual('\n\n'.join(segments), text)

    def test_long_sentence_and_short_tail_stay_together(self):
        first, second = self.text.split('\n\n')
        text = first.replace('。', '，') + second.replace('。', '，') + '就这些。'
        self.assertEqual(split_reply(text), (text,))
        self.assertEqual(split_reply(first + second + '好。'), (first, second + '好。'))

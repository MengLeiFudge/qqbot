import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

// 账号集合由部署脚本从账号清单生成；绑定框架的账号由各自插件处理。
let accountIds = new Set();
const pendingRequests = new Set();
const approvedRequests = new Set();
const MAX_APPROVED_REQUESTS = 1024;

/** 加载仅保留 NapCat 的账号集合，配置无效时阻止插件加载。 */
export async function plugin_init(ctx) {
  const configPath = join(ctx.pluginPath, 'accounts.json');
  const accounts = JSON.parse(await readFile(configPath, 'utf8'));
  if (!Array.isArray(accounts) || accounts.some(id => typeof id !== 'string' || !/^\d+$/.test(id))) {
    throw new Error(`社交请求账号配置无效：${configPath}`);
  }
  accountIds = new Set(accounts);
  pendingRequests.clear();
  approvedRequests.clear();
  ctx.logger.info(`自动同意好友和群请求已启用，负责 ${accountIds.size} 个仅使用 NapCat 的账号`);
}

/** 同意所属账号的好友、群邀请和成员申请；不发送聊天消息。 */
export async function plugin_onevent(ctx, event) {
  if (event.post_type !== 'request' || !accountIds.has(String(event.self_id))) {
    return;
  }

  const requestType = String(event.request_type ?? '');
  const subType = String(event.sub_type ?? '');
  let action;
  if (requestType === 'friend') {
    action = 'set_friend_add_request';
  } else if (requestType === 'group' && (subType === 'add' || subType === 'invite')) {
    action = 'set_group_add_request';
  } else {
    return;
  }

  const flag = String(event.flag ?? '').trim();
  if (!flag) {
    ctx.logger.warn(`请求缺少 flag，无法自动同意：${requestType}.${subType}`);
    return;
  }
  const key = `${event.self_id}:${action}:${subType}:${flag}`;
  if (pendingRequests.has(key) || approvedRequests.has(key)) {
    return;
  }

  const params = { flag, approve: true };
  if (requestType === 'group') {
    params.sub_type = subType;
  }
  // 在等待动作前占用该申请，避免并发上报重复执行。
  pendingRequests.add(key);
  try {
    await ctx.actions.call(action, params, ctx.adapterName, ctx.pluginManager.config);
    approvedRequests.add(key);
    if (approvedRequests.size > MAX_APPROVED_REQUESTS) {
      approvedRequests.delete(approvedRequests.values().next().value);
    }
    ctx.logger.info(`已自动同意请求：action=${action} self_id=${event.self_id} user_id=${event.user_id ?? ''} group_id=${event.group_id ?? ''}`);
  } catch (error) {
    // 失败不进入成功缓存，保留下次重新上报时的处理机会。
    ctx.logger.error(`自动同意请求失败：action=${action} self_id=${event.self_id}`, error);
  } finally {
    pendingRequests.delete(key);
  }
}

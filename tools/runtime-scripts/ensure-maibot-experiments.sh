#!/usr/bin/env bash
set -euo pipefail

force_restart=false
if [[ "${1:-}" == "--force-restart" ]]; then
  force_restart=true
  shift
fi
if (($#)); then
  echo "Usage: $0 [--force-restart]" >&2
  exit 2
fi

instances=(
  "/mnt/d/project/maibot|Yuecheng|8001|8095"
  "/mnt/d/project/maibot-xingyao|Xingyao|8002|8096"
)

find_instance_runner_pids() {
  local root="$1"
  local proc pid cwd cmdline
  for proc in /proc/[0-9]*; do
    pid="${proc##*/}"
    cwd="$(readlink "$proc/cwd" 2>/dev/null || true)"
    [[ "$cwd" == "$root" ]] || continue
    cmdline="$(tr '\0' ' ' <"$proc/cmdline" 2>/dev/null || true)"
    [[ "$cmdline" == *"bot.py"* ]] || continue
    printf '%s\n' "$pid"
  done
}

web_ready() {
  local port="$1"
  curl -fsS --max-time 3 "http://127.0.0.1:${port}/" >/dev/null 2>&1
}

onebot_connected_for_root() {
  local root="$1"
  local port="$2"
  local line pid cwd
  while IFS= read -r line; do
    [[ "$line" == *"127.0.0.1:${port}"* ]] || continue
    while [[ "$line" =~ pid=([0-9]+) ]]; do
      pid="${BASH_REMATCH[1]}"
      cwd="$(readlink "/proc/${pid}/cwd" 2>/dev/null || true)"
      [[ "$cwd" == "$root" ]] && return 0
      line="${line#*pid=${pid}}"
    done
  done < <(ss -Htnp state established 2>/dev/null || true)
  return 1
}

instance_ready() {
  local root="$1"
  local web_port="$2"
  local onebot_port="$3"
  local runners
  runners="$(find_instance_runner_pids "$root")"
  [[ -n "$runners" ]] && web_ready "$web_port" && onebot_connected_for_root "$root" "$onebot_port"
}

stop_instance() {
  local root="$1"
  local pid pgid
  declare -A groups=()
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ' || true)"
    [[ "$pgid" =~ ^[0-9]+$ ]] && groups["$pgid"]=1
  done < <(find_instance_runner_pids "$root")

  for pgid in "${!groups[@]}"; do
    kill -TERM -- "-${pgid}" 2>/dev/null || true
  done
  local deadline=$((SECONDS + 20))
  while [[ $SECONDS -lt $deadline ]] && [[ -n "$(find_instance_runner_pids "$root")" ]]; do
    sleep 1
  done
  for pgid in "${!groups[@]}"; do
    kill -KILL -- "-${pgid}" 2>/dev/null || true
  done
}

start_instance() {
  local root="$1"
  local label="$2"
  mkdir -p "$root/logs/runtime"
  local stamp log_file
  stamp="$(date +%Y%m%d-%H%M%S)"
  log_file="$root/logs/runtime/maibot-${label,,}-${stamp}.log"
  (
    cd "$root"
    nohup setsid .venv/bin/python bot.py >>"$log_file" 2>&1 </dev/null &
  )
}

ensure_instance() {
  local root="$1"
  local label="$2"
  local web_port="$3"
  local onebot_port="$4"

  [[ -f "$root/bot.py" ]] || { echo "[MaiBot] [$label] missing instance root: $root" >&2; return 1; }
  [[ -x "$root/.venv/bin/python" ]] || { echo "[MaiBot] [$label] missing Python environment" >&2; return 1; }

  if $force_restart && [[ -n "$(find_instance_runner_pids "$root")" ]]; then
    echo "[MaiBot] [$label] force restart requested"
    stop_instance "$root"
  fi

  if instance_ready "$root" "$web_port" "$onebot_port"; then
    echo "[MaiBot] [$label] ready: web=$web_port onebot=$onebot_port"
    return 0
  fi

  if [[ -n "$(find_instance_runner_pids "$root")" ]]; then
    local grace_deadline=$((SECONDS + 90))
    while [[ $SECONDS -lt $grace_deadline ]]; do
      if instance_ready "$root" "$web_port" "$onebot_port"; then
        echo "[MaiBot] [$label] reconnected: web=$web_port onebot=$onebot_port"
        return 0
      fi
      sleep 3
    done
    echo "[MaiBot] [$label] stale runtime detected; restarting"
    stop_instance "$root"
  fi

  start_instance "$root" "$label"
  local ready_deadline=$((SECONDS + 240))
  while [[ $SECONDS -lt $ready_deadline ]]; do
    if instance_ready "$root" "$web_port" "$onebot_port"; then
      echo "[MaiBot] [$label] started: web=$web_port onebot=$onebot_port"
      return 0
    fi
    sleep 3
  done

  echo "[MaiBot] [$label] startup timed out: web=$web_port onebot=$onebot_port" >&2
  return 1
}

for item in "${instances[@]}"; do
  IFS='|' read -r root label web_port onebot_port <<<"$item"
  ensure_instance "$root" "$label" "$web_port" "$onebot_port"
done

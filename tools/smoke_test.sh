#!/usr/bin/env bash
# ==============================================================================
# 白虎面板应用受控子任务烟测脚本 (Smoke-Test Installed Task with Baihu CLI)
# ==============================================================================
set -euo pipefail

export DB_TYPE="${DB_TYPE:-sqlite}"
export DB_DSN="${DB_DSN:-./baihu_ci_test.db}"

echo "=================================================="
echo ">> 启动轻量白虎后台服务进行任务原生测试"
echo "=================================================="
./baihu server &
SERVER_PID=$!

# 退出时确保自动清理后台服务进程
cleanup() {
  echo ">> 正在关闭后台测试服务 (PID: ${SERVER_PID})..."
  kill "${SERVER_PID}" 2>/dev/null || true
}
trap cleanup EXIT

# 轮询探测后台 HTTP 服务端口 (8052) 是否真正就绪 (最多等待 20 秒)
echo ">> 正在等待白虎后台服务在 8052 端口监听就绪..."
for i in {1..20}; do
  if curl -s -m 1 http://127.0.0.1:8052/ >/dev/null 2>&1 || curl -s -m 1 http://127.0.0.1:8052/api/v1/health >/dev/null 2>&1; then
    echo ">> 白虎后台服务已就绪！"
    break
  fi
  sleep 1
done

# 输出当前已安装任务清单
echo ">> 当前已安装任务列表:"
./baihu task list

# 智能提取已安装的受控子任务 ID (严格过滤 -type task，优先选取已启用且具代表性的日常/自检核心任务)
TASK_ID=$(./baihu task list -type task 2>/dev/null | grep -E "\|\s*启用\s*$" | grep -Ei "自检|check|daily|基础|经验|main" | head -n 1 | awk '{print $1}' || true)
if [ -z "$TASK_ID" ]; then
  TASK_ID=$(./baihu task list -type task 2>/dev/null | grep -E "\|\s*启用\s*$" | head -n 1 | awk '{print $1}' || true)
fi
if [ -z "$TASK_ID" ]; then
  TASK_ID=$(./baihu task list -type task 2>/dev/null | grep -E "\|\s*(启用|禁用)\s*$" | head -n 1 | awk '{print $1}' || true)
fi

if [ -n "$TASK_ID" ]; then
  echo "=================================================="
  echo ">> 智能选定已安装测试任务 ID: $TASK_ID"
  echo ">> 通过白虎原生 CLI 触发任务执行: ./baihu task run $TASK_ID"
  echo "=================================================="
  RUN_OUTPUT=$(./baihu task run "$TASK_ID" 2>&1 || true)
  echo "$RUN_OUTPUT"
  if echo "$RUN_OUTPUT" | grep -q "任务触发失败"; then
    echo "[FATAL] 任务触发失败！" >&2
    exit 1
  fi

  # 轮询等待任务产生具体执行日志 (最多等待 20 秒)
  echo ">> 正在等待任务拉起并捕获控制台具体输出..."
  STATUS_OUTPUT=""
  HAS_LOG=false
  for i in {1..20}; do
    sleep 1
    STATUS_OUTPUT=$(./baihu task status "$TASK_ID" 2>&1 || true)
    if echo "$STATUS_OUTPUT" | grep -q "日志记录:"; then
      HAS_LOG=true
      if ! echo "$STATUS_OUTPUT" | grep -q "最终状态: 运行中"; then
        break
      fi
    fi
  done

  echo "===================================================================================================="
  echo ">> [任务具体执行状态与完整回显详情]:"
  echo "$STATUS_OUTPUT"
  echo "===================================================================================================="

  if [ "$HAS_LOG" != "true" ]; then
    echo "[FATAL] 任务下发后超时未生成执行日志！" >&2
    exit 1
  fi

  # 核心判定：只抓基本文件缺失或命令不存在的系统级故障，业务逻辑报错安全放行
  if echo "$STATUS_OUTPUT" | grep -Eiq "couldn't exec process: No such file|No such file or directory|command not found|Cannot find module|not found in \$PATH|Permission denied"; then
    echo "==================================================" >&2
    echo "[FATAL] 任务健全性校验失败：检测到可执行文件或入口脚本缺失！" >&2
    echo "==================================================" >&2
    exit 1
  fi

  echo ">> ✓ 任务已真实拉起并完成执行！基本文件与环境完整就绪。"
else
  echo ">> 提示: 当前应用未注册受控子任务，跳过单任务测试。"
fi

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
白虎应用商店 - wxread-panel (wlunan/wxread-panel) 声明式构建器
------------------------------------------------------------
作用:
  从上游开源仓库 (https://github.com/wlunan/wxread-panel.git) 获取最新状态，
  派生上游事实字段，并据此生成符合白虎应用规范 (Baihu App Specification v1)
  的 apps/wxread-panel/app.yaml。本文件即 app.yaml 的唯一生成源。

派生来源 (上游真相):
  1. last_commit             <- git log -1 --format=%cI
  2. env_schema 的 key 集合  <- 正则扫描上游 config.py 中的 getenv('KEY') 调用，并做一致性断言
  其余展示层 / 调度层字段 (description、icon、scenarios、tasks 等) 来自本文件内置的规范模板。

构建期自检 (_validate):
  - 根节点物理顺序符合 build-note 第九节
  - env_schema 覆盖上游 config.py 中全部 getenv() 变量，且不引入上游不存在的变量
  - 所有 Cron 表达式为 6 位秒级格式
  - scenarios 有且仅有一个默认场景，且 task_presets 键与 tasks[].id 严格一致

使用方式:
  python build.py [--source-dir <路径>] [--output <路径>] [--proxy <代理前缀>]
"""

import re
import sys
import argparse
import subprocess
import tempfile
from pathlib import Path

import yaml

UPSTREAM_REPO = "https://github.com/wlunan/wxread-panel.git"
UPSTREAM_BRANCH = "master"

# 无法联网克隆上游时的兜底值；正常路径一律从上游 git 读取，不走这里
FALLBACK_LAST_COMMIT = "2026-10-02T14:50:00+08:00"

# 根节点物理顺序规范 (build-note 第九节)
SPEC_ROOT_KEY_ORDER = [
    "spec_version",
    "id",
    "name",
    "version",
    "author",
    "category",
    "last_commit",
    "template",
    "description",
    "icon",
    "homepage",
    "build_opts",
    "schedule_opts",
    "sources",
    "setup",
    "env_schema",
    "sync_rules",
    "scenarios",
]

# 匹配 config.py 中的 getenv('XXX') 调用；函数定义与 getenv(key) 透传都不会命中
ENV_KEY_RE = re.compile(r"getenv\(\s*['\"]([A-Z0-9_]+)['\"]")


def clone_upstream_repo(proxy: str = ""):
    """浅克隆上游仓库到临时目录；遇网络波动自动尝试镜像加速。失败返回 None"""
    proxies_to_try = [proxy] if proxy else ["", "https://gh-proxy.com/", "https://ghfast.top/"]

    for p in proxies_to_try:
        tmp_dir = tempfile.TemporaryDirectory(prefix="baihu_wxread_")
        repo_url = UPSTREAM_REPO
        if p:
            repo_url = f"{p.rstrip('/')}/{UPSTREAM_REPO}"

        print(f"[克隆] 正在尝试拉取上游最新仓库: {repo_url} (分支: {UPSTREAM_BRANCH})...")
        res = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", UPSTREAM_BRANCH, repo_url, tmp_dir.name],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            print(f"[成功] 上游仓库已拉取至临时目录: {tmp_dir.name}")
            return tmp_dir

        err_msg = res.stderr.strip().splitlines()[-1] if res.stderr.strip() else "未知网络异常"
        print(f"[警告] 当前地址拉取失败 ({err_msg})，尝试后续加速方案...")
        tmp_dir.cleanup()

    print("[警告] 所有远程克隆均失败。", file=sys.stderr)
    return None


def get_repo_last_commit_time(repo_dir: Path) -> str:
    """ 取上游最后一次 commit 时间 (ISO 8601, 含时区偏移) """
    if not repo_dir or not repo_dir.exists():
        return ""
    res = subprocess.run(
        ["git", "log", "-1", "--format=%cI"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
    )
    return res.stdout.strip() if res.returncode == 0 else ""


def scan_upstream_env_keys(repo_dir: Path):
    """ 扫描上游 config.py，提取全部 getenv('KEY') 中的环境变量名 """
    config_py = repo_dir / "config.py"
    if not config_py.exists():
        print(f"[警告] 上游未找到 config.py，跳过环境变量一致性校验: {config_py}", file=sys.stderr)
        return None
    content = config_py.read_text(encoding="utf-8", errors="ignore")
    return set(ENV_KEY_RE.findall(content))


def generate_app_yaml(last_commit: str) -> str:
    """ 把派生出的上游事实注入内置规范模板，输出 app.yaml 全文 """
    return f'''# ==============================================================================
# 白虎面板应用规范定义文件 (Baihu Application Specification v1)
# 应用标识: wxread-panel
# 上游仓库: {UPSTREAM_REPO}
# 本文件由 apps/wxread-panel/build.py 自动构建生成 (请勿手动修改)
#
# 【用户前置条件】本应用不走账号密码登录，必须由用户在微信读书网页端自行抓包获取
# WXREAD_CURL_BASH 凭证。用户侧引导文案统一收敛在三处，请勿分散：
#   1) description  —— 详情页总览（告知"用前必须抓包"）
#   2) env_schema.WXREAD_CURL_BASH 的 label / description / placeholder —— 安装表单就地引导
#   3) tasks.read.remark —— 任务列表二次提示（凭证缺失/过期会导致失败）
# 抓包步骤（供维护者核对，用户侧文案为同一套流程）：
#   1. 电脑浏览器登录 https://weread.qq.com/ 并打开《三体》等书籍，点『下一页』
#   2. F12 开发者工具 -> Network 面板，筛选 read
#   3. 命中 https://weread.qq.com/web/book/read 请求，右键 Copy as cURL (bash)
#   4. 整段粘贴进安装表单的 WXREAD_CURL_BASH 字段（返回含 synckey 即为有效）
# ==============================================================================

spec_version: "v1"
id: "wxread-panel"
name: "微信读书自动阅读"
version: "1.0.0"
author: "wlunan"
category: "福利签到"
last_commit: "{last_commit}"
template:
  - tag: "WxReadPanel"
  - mise_languages: "python@3.13.12"
description: "微信读书自动阅读的多面板通用版。【使用前必读】本应用不使用账号密码登录，需自行抓包配置 WXREAD_CURL_BASH 凭证：登录 weread.qq.com 打开书籍翻到下一页，按 F12 抓取 https://weread.qq.com/web/book/read 请求并复制为 Bash 格式，整段粘贴进安装表单。支持目标总时长与请求间隔随机、synckey 自动修复、鉴权失效自动刷新 Cookie，并可推送至 PushPlus / WxPusher / Telegram / ServerChan。抓包图文步骤见上游项目主页 README『操作步骤 → 抓包准备』章节。"
icon: "https://weread.qq.com/favicon.ico"
homepage: "https://github.com/wlunan/wxread-panel"

# ------------------------------------------------------------------------------
# 0. 高级构建与部署控制预设 (Build Opts)
# ------------------------------------------------------------------------------
build_opts:
  force_setup: false                  # 依赖探活已足够廉价，无需每次强制重装
  skip_setup: false
  skip_sync: false
  overwrite_env: false
  overwrite_task: true

# ------------------------------------------------------------------------------
# 0.1 应用主任务调度规则与策略预设 (Schedule Opts)
# ------------------------------------------------------------------------------
# 目标阅读时长区间最长为 60 分钟，超时需放宽，否则任务会被中途强杀
schedule_opts:
  schedule: "0 0 7 * * *"
  random_range: 0
  timeout: 90
  retry_count: 0
  retry_interval: 0

# ------------------------------------------------------------------------------
# 1. 脚本代码源列表 (Sources)
# ------------------------------------------------------------------------------
sources:
  - id: "main"
    source_type: "git"
    source_url: "{UPSTREAM_REPO}"
    branch: "{UPSTREAM_BRANCH}"
    path: ""
    single_file: false
    proxy: "ghproxy"
    target_path: "main"

# ------------------------------------------------------------------------------
# 2. 原生 Shell 环境与依赖编排 (Setup)
# ------------------------------------------------------------------------------
setup:
  # 依赖快速探测：requests 已就绪则退出码 0，秒级跳过安装
  check: "mise exec {{mise_languages}} -- python -c \\"import requests\\""

  # 复用镜像预装 python@3.13.12，仅补装 requests
  install: |
    mise install {{mise_languages}}
    echo ">> 正在安装微信读书脚本 Python 依赖..."
    mise exec {{mise_languages}} -- python -m pip install --no-cache-dir -r "{{app_dir}}/main/requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple
    echo ">> 依赖环境准备就绪！"

  post_install: |
    echo ">> 后置初始化准备就绪！"

  # 跨平台清理：只清理应用自身的字节码缓存，不依赖 rm -rf
  # 注意：不要 pip uninstall requests —— 那会动到 mise 全局共享的 python 环境，可能连带破坏其它应用的依赖
  uninstall: |
    mise exec {{mise_languages}} -- python -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path(r'{{app_dir}}/main').rglob('__pycache__')]"

# ------------------------------------------------------------------------------
# 3. 环境变量声明契约 (Env Schema)
# ------------------------------------------------------------------------------
env_schema:
  - key: "WXREAD_CURL_BASH"
    label: "read 接口凭证 (需自行抓包，必填)"
    type: "secret"
    required: true
    description: "必填！本应用需自行抓包：电脑浏览器登录 weread.qq.com 并打开一本已购/免费书籍，点『下一页』；按 F12 打开开发者工具切到 Network 面板，筛选 read；找到 https://weread.qq.com/web/book/read 请求后右键选择 Copy as cURL (bash)，将整段命令原样粘贴到此处。该接口返回 succ=1 且带 synckey 字段即为有效凭证。凭证随登录会话过期失效，届时需重新抓包并更新本字段。"
    placeholder: "curl https://weread.qq.com/web/book/read -H ... --data-raw ..."

  - key: "READ_TIME_MIN"
    label: "目标阅读时长下限 (分钟)"
    type: "number"
    required: false
    default: 20
    description: "每次运行在该区间内随机取目标总时长；只想完成签到可设为 1"

  - key: "READ_TIME_MAX"
    label: "目标阅读时长上限 (分钟)"
    type: "number"
    required: false
    default: 60
    description: "与下限填相同值即可固定时长"

  - key: "READ_INTERVAL_MIN"
    label: "单次阅读间隔下限 (秒)"
    type: "number"
    required: false
    default: 20
    description: "约等于服务端单次计入的阅读时长，不建议大幅偏离 30"

  - key: "READ_INTERVAL_MAX"
    label: "单次阅读间隔上限 (秒)"
    type: "number"
    required: false
    default: 40

  - key: "READ_NUM"
    label: "兼容旧参数：阅读次数"
    type: "number"
    required: false
    default: 40
    description: "已弃用（兼容保留），仅当未配置 READ_TIME_* 时生效，等价于 次数 × 30 秒"

  - key: "PUSH_METHOD"
    label: "推送方式"
    type: "select"
    required: false
    default: ""
    options:
      - label: "不推送"
        value: ""
      - label: "PushPlus"
        value: "pushplus"
      - label: "WxPusher"
        value: "wxpusher"
      - label: "Telegram"
        value: "telegram"
      - label: "ServerChan"
        value: "serverchan"

  - key: "PUSHPLUS_TOKEN"
    label: "PushPlus Token"
    type: "secret"
    required: false
    description: "当 PUSH_METHOD=pushplus 时必填"

  - key: "WXPUSHER_SPT"
    label: "WxPusher SPT"
    type: "secret"
    required: false
    description: "当 PUSH_METHOD=wxpusher 时必填"

  - key: "TELEGRAM_BOT_TOKEN"
    label: "Telegram 机器人 Token"
    type: "secret"
    required: false
    description: "当 PUSH_METHOD=telegram 时必填"

  - key: "TELEGRAM_CHAT_ID"
    label: "Telegram 群组 / 会话 ID"
    type: "string"
    required: false
    description: "当 PUSH_METHOD=telegram 时必填"

  - key: "SERVERCHAN_SPT"
    label: "ServerChan SendKey"
    type: "secret"
    required: false
    description: "当 PUSH_METHOD=serverchan 时必填"

# ------------------------------------------------------------------------------
# 4. 任务生成与调度映射 (Sync Rules / Tasks)
# ------------------------------------------------------------------------------
sync_rules:
  defaults:
    timeout: 90                       # 与 schedule_opts 一致，覆盖 60 分钟最长阅读
    retry_count: 0
    retry_interval: 0
    work_dir: "{{app_dir}}/main"        # 必须与脚本同目录，保证 from config import 生效
    language: "{{mise_languages}}"

  tasks:
    - id: "read"
      name: "微信读书自动阅读"
      source: "main"
      language: "{{mise_languages}}"
      command: "python main.py"
      default_cron: "0 0 7 * * *"
      enabled: true
      remark: "首次运行前必须先完成 WXREAD_CURL_BASH 抓包配置，否则会因登录状态失效而失败；凭证过期后需重新抓包更新。任务会按 READ_TIME_MIN~READ_TIME_MAX 随机读够指定时长，单次运行可能长达 1 小时，请勿中途中断或把超时设得过短。"

# ------------------------------------------------------------------------------
# 5. 使用场景模板 (Scenarios)
# ------------------------------------------------------------------------------
scenarios:
  - id: "standard"
    name: "每日清晨自动阅读（推荐）"
    description: "每天 07:00 自动阅读，时长在 READ_TIME_MIN~READ_TIME_MAX 区间内随机"
    default: true
    task_presets:
      read:
        enabled: true

  - id: "evening"
    name: "夜间静默阅读"
    description: "改到每天 22:30 执行，适合白天不方便挂机"
    task_presets:
      read:
        enabled: true
        cron: "0 30 22 * * *"

  - id: "manual"
    name: "仅保留任务（手动触发）"
    description: "同步任务但不自动定时，需要时在面板手动运行"
    task_presets:
      read:
        enabled: false
'''


def _validate(content: str, upstream_env_keys):
    """ 构建期自检；返回错误信息列表（空列表表示通过） """
    errors = []
    doc = yaml.safe_load(content)

    if list(doc.keys()) != SPEC_ROOT_KEY_ORDER:
        errors.append(
            f"根节点顺序不符合规范第九节。\n  期望: {SPEC_ROOT_KEY_ORDER}\n  实际: {list(doc.keys())}"
        )

    declared = {item["key"] for item in doc.get("env_schema") or []}
    if upstream_env_keys is not None:
        missing = sorted(upstream_env_keys - declared)
        unknown = sorted(declared - upstream_env_keys)
        if missing:
            errors.append(f"上游 config.py 新增了未登记的环境变量，请补齐 env_schema: {missing}")
        if unknown:
            errors.append(f"env_schema 声明了上游 config.py 中不存在的变量: {unknown}")

    crons = [doc["schedule_opts"]["schedule"]]
    tasks = (doc.get("sync_rules") or {}).get("tasks") or []
    crons += [t["default_cron"] for t in tasks if t.get("default_cron")]
    for scenario in doc.get("scenarios") or []:
        crons += [p["cron"] for p in (scenario.get("task_presets") or {}).values() if p.get("cron")]
    bad_crons = [c for c in crons if len(c.split()) != 6]
    if bad_crons:
        errors.append(f"存在非 6 位秒级 Cron 表达式: {bad_crons}")

    task_ids = {t["id"] for t in tasks}
    scenarios = doc.get("scenarios") or []
    default_count = sum(1 for s in scenarios if s.get("default"))
    if default_count != 1:
        errors.append(f"必须且只能有一个默认场景，当前为 {default_count} 个")
    for scenario in scenarios:
        preset_ids = set(scenario.get("task_presets") or {})
        if preset_ids != task_ids:
            errors.append(
                f"场景 \"{scenario['id']}\" 的 task_presets 与 tasks[].id 不一致: "
                f"{sorted(preset_ids)} != {sorted(task_ids)}"
            )

    return errors


def main():
    parser = argparse.ArgumentParser(description="wxread-panel app.yaml Manifest 自动构建器")
    parser.add_argument("-s", "--source-dir", help="可选：本地已有上游源码目录（留空则自动从 GitHub 浅克隆）")
    parser.add_argument("-o", "--output", help="生成的 app.yaml 输出路径", default="app.yaml")
    parser.add_argument("-p", "--proxy", help="克隆 GitHub 代理前缀 (例如 https://gh-proxy.com/)", default="")
    args = parser.parse_args()

    print("==================================================")
    print("白虎应用商店 - wxread-panel 构建流水线")
    print("==================================================")

    tmp_dir_handle = None
    repo_dir = None
    last_commit = ""

    if args.source_dir and Path(args.source_dir).exists():
        repo_dir = Path(args.source_dir).resolve()
        print(f"[源目录] 使用指定的本地上游目录: {repo_dir}")
    else:
        tmp_dir_handle = clone_upstream_repo(args.proxy)
        if tmp_dir_handle:
            repo_dir = Path(tmp_dir_handle.name)

    try:
        if repo_dir:
            last_commit = get_repo_last_commit_time(repo_dir)
            upstream_env_keys = scan_upstream_env_keys(repo_dir)
            print(f"[派生] last_commit = {last_commit or '(未取到)'}")
            if upstream_env_keys is not None:
                print(f"[派生] 上游环境变量 {len(upstream_env_keys)} 个: {sorted(upstream_env_keys)}")
        else:
            print("[警告] 无法获取上游仓库，回退到内置兜底模板生成。", file=sys.stderr)
            upstream_env_keys = None

        if not last_commit:
            last_commit = FALLBACK_LAST_COMMIT
            print(f"[警告] 未能从上游读取提交时间，使用兜底值: {last_commit}", file=sys.stderr)

        print("\n[生成] 正在组装白虎规范应用配置清单 (v1)...")
        content = generate_app_yaml(last_commit)

        print("[自检] 正在执行构建期校验...")
        errors = _validate(content, upstream_env_keys)
        if errors:
            for err in errors:
                print(f"[失败] {err}", file=sys.stderr)
            sys.exit(1)
        print("[自检] 通过：根节点顺序、环境变量覆盖、Cron 位数、场景映射均一致")

        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = Path(__file__).resolve().parent / output_path
        # 固定写入 LF 与 UTF-8，避免 Windows 本地生成 CRLF 造成无意义 diff
        output_path.write_bytes(content.encode("utf-8"))
        print(f"\n[完成] 已生成: {output_path}")
        print(f"       文件大小: {output_path.stat().st_size} 字节")
    finally:
        if tmp_dir_handle:
            print(f"[清理] 正在清理临时工作区: {tmp_dir_handle.name}...")
            tmp_dir_handle.cleanup()

    print("==================================================")


if __name__ == "__main__":
    main()

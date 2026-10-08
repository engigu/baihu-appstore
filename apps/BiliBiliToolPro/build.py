#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BiliBiliToolPro 白虎应用构建脚本 (Manifest Builder)
------------------------------------------------------------
作用:
  从上游开源仓库 (https://github.com/RayWangQvQ/BiliBiliToolPro.git)
  拉取并自动扫描提取 baihu 适配逻辑、任务列表、环境依赖、环境变量契约与场景模板，
  自动构建生成符合白虎应用规范 (Baihu App Specification v1) 的 app.yaml。

使用方式:
  python build.py [--source-dir <路径>] [--output <路径>] [--proxy <代理前缀>]
"""

import os
import sys
import re
import shutil
import tempfile
import argparse
import subprocess
from pathlib import Path

UPSTREAM_REPO = "https://github.com/RayWangQvQ/BiliBiliToolPro.git"
UPSTREAM_BRANCH = "main"


def fetch_latest_release_info(proxy: str = "") -> dict:
    """尝试通过 GitHub API 获取最新 Release 版本号与 Tag"""
    import urllib.request
    import json

    api_url = "https://api.github.com/repos/RayWangQvQ/BiliBiliToolPro/releases/latest"
    headers = {"User-Agent": "BaihuAppStore-Builder", "Accept": "application/vnd.github.v3+json"}
    
    # 优先尝试 gh CLI
    try:
        res = subprocess.run(
            ["gh", "api", "repos/RayWangQvQ/BiliBiliToolPro/releases/latest"],
            capture_output=True,
            text=True
        )
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            tag = data.get("tag_name", "").strip()
            published_at = data.get("published_at", "").strip()
            if tag:
                clean_ver = tag.lstrip("vV")
                return {"version": clean_ver, "tag": tag, "published_at": published_at}
    except Exception:
        pass

    # 次选 urllib 直连获取
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            tag = data.get("tag_name", "").strip()
            published_at = data.get("published_at", "").strip()
            if tag:
                clean_ver = tag.lstrip("vV")
                return {"version": clean_ver, "tag": tag, "published_at": published_at}
    except Exception:
        pass

    return {}


def clone_upstream_repo(proxy: str = "", branch_or_tag: str = "main") -> tempfile.TemporaryDirectory:
    """克隆上游仓库到临时目录（深度为 1 浅克隆，遇到网络波动自动尝试镜像加速）"""
    proxies_to_try = [proxy] if proxy else ["", "https://gh-proxy.com/", "https://ghfast.top/"]

    for p in proxies_to_try:
        tmp_dir = tempfile.TemporaryDirectory(prefix="baihu_bili_")
        repo_url = UPSTREAM_REPO
        if p:
            proxy_clean = p.rstrip("/") + "/"
            repo_url = f"{proxy_clean}{UPSTREAM_REPO}"

        print(f"[克隆] 正在尝试拉取上游仓库: {repo_url} (分支/标签: {branch_or_tag})...")
        cmd = [
            "git", "clone",
            "--depth", "1",
            "--branch", branch_or_tag,
            repo_url,
            tmp_dir.name
        ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"[成功] 上游仓库已成功拉取至临时目录: {tmp_dir.name}")
            return tmp_dir
        else:
            err_msg = res.stderr.strip().splitlines()[-1] if res.stderr.strip() else "未知网络异常"
            print(f"[警告] 当前地址拉取失败 ({err_msg})，尝试后续加速方案...")
            tmp_dir.cleanup()

    print(f"[错误] 所有远程克隆均失败。", file=sys.stderr)
    return None


def parse_tasks_from_repo(repo_dir: Path):
    """
    扫描 BiliBiliToolPro/qinglong/DefaultTasks 与 baihu/DefaultTasks
    提取任务脚本中的元数据 (cron, Env 名称, target_task_code)
    """
    tasks = []
    task_dirs = [
        repo_dir / "qinglong" / "DefaultTasks",
        repo_dir / "baihu" / "DefaultTasks",
    ]

    scanned_codes = set()
    friendly_names = {
        "Daily": "每日基础经验与投币任务",
        "Login": "扫码登录 (自动持久化Cookie)",
        "LiveLottery": "天选时刻高频巡检抽奖",
        "Manga": "漫画任务",
        "MangaPrivilege": "大会员漫画权益领取",
        "Silver2Coin": "直播间银瓜子兑换硬币",
        "VipBigPoint": "大会员大积分日常任务",
        "VipPrivilege": "大会员专属福利领取",
        "Charge": "大会员每月B币券充电",
        "LiveFansMedal": "直播粉丝牌亲密度打卡",
        "UnfollowBatched": "批量取关失效主播",
        "Test": "Cookie 有效性测试",
        "TryFix": "清理缓存并重新预编译 (尝试修复异常)",
    }

    # 核心日常默认启用的任务
    default_enabled_codes = {"Daily", "Manga", "MangaPrivilege", "Silver2Coin", "VipBigPoint"}

    for t_dir in task_dirs:
        if not t_dir.exists():
            continue

        for sh_file in sorted(t_dir.glob("bili_task_*.sh")):
            filename = sh_file.name
            if filename in ("bili_task_base.sh", "bili_dev_task_base.sh"):
                continue

            try:
                content = sh_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            # 提取 target_task_code
            m_target = re.search(r'target_task_code=["\']?([a-zA-Z0-9_]+)["\']?', content)
            target_code = m_target.group(1) if m_target else None

            # 若未显式定义，从文件名推断
            if not target_code:
                stem = sh_file.stem.replace("bili_task_", "")
                target_code = stem[0].upper() + stem[1:] if stem else "Daily"

            if target_code in scanned_codes:
                continue
            scanned_codes.add(target_code)

            # 提取 cron
            m_cron = re.search(r'#\s*cron:\s*([^\r\n]+)', content)
            cron = m_cron.group(1).strip() if m_cron else "0 0 9 * * *"
            parts = cron.split()
            if len(parts) == 5:
                cron = "0 " + cron

            # 提取 Env 名称
            m_env = re.search(r'#\s*new Env\(["\']([^"\']+)["\']\)', content)
            raw_env_name = m_env.group(1).strip() if m_env else target_code

            # 生成友好展示名称
            display_name = friendly_names.get(target_code)
            if not display_name:
                display_name = raw_env_name
                if display_name.startswith("bili"):
                    display_name = display_name[4:]

            # 规范任务 ID
            task_id = re.sub(r'(?<!^)(?=[A-Z])', '_', target_code).lower()
            enabled = target_code in default_enabled_codes

            if target_code == "TryFix":
                cmd = "./Ray.BiliBiliTool.Console --ENVIRONMENT=Production --runTasks=Test"
            else:
                cmd = f"./Ray.BiliBiliTool.Console --ENVIRONMENT=Production --runTasks={target_code}"

            tasks.append({
                "id": task_id,
                "name": display_name,
                "target_code": target_code,
                "cron": cron,
                "enabled": enabled,
                "command": cmd,
            })

    # 如果未能从目录中扫描到，使用标准缺省任务集兜底
    if not tasks:
        fallback_targets = [
            ("daily", "每日基础经验与投币任务", "Daily", "0 0 9 * * *", True),
            ("login", "扫码登录 (自动持久化Cookie)", "Login", "0 0 1 1 *", False),
            ("live_lottery", "天选时刻高频巡检抽奖", "LiveLottery", "*/15 * * * *", False),
            ("manga", "漫画权益自动领取", "Manga", "0 30 10 * * *", True),
            ("silver2coin", "直播间银瓜子兑换硬币", "Silver2Coin", "0 5 0 * * *", True),
            ("vip_bigpoint", "大会员大积分日常任务", "VipBigPoint", "0 15 1 * * *", True),
            ("charge", "大会员每月B币券充电", "Charge", "0 0 12 28 * *", False),
        ]
        for t_id, t_name, t_code, t_cron, t_en in fallback_targets:
            if t_code == "TryFix":
                cmd = "./Ray.BiliBiliTool.Console --ENVIRONMENT=Production --runTasks=Test"
            else:
                cmd = f"./Ray.BiliBiliTool.Console --ENVIRONMENT=Production --runTasks={t_code}"

            tasks.append({
                "id": t_id,
                "name": t_name,
                "target_code": t_code,
                "cron": t_cron,
                "enabled": t_en,
                "command": cmd,
            })

    return tasks


def get_repo_last_commit_time(repo_dir: Path) -> str:
    """获取 git 仓库的最后一次 commit 提交时间 (ISO 8601 格式)"""
    if not repo_dir or not repo_dir.exists():
        return ""
    try:
        res = subprocess.run(
            ["git", "log", "-1", "--format=%cI"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return ""


def get_repo_version(repo_dir: Path, fallback_version: str = "4.1.1") -> str:
    """从 common.props 文件提取真实版本号"""
    if repo_dir:
        props_file = repo_dir / "common.props"
        if props_file.exists():
            try:
                content = props_file.read_text(encoding="utf-8")
                match = re.search(r"<Version>(.*?)</Version>", content)
                if match and match.group(1).strip():
                    return match.group(1).strip()
            except Exception:
                pass
    return fallback_version


def generate_app_yaml(tasks, version="4.1.1", source_ref="4.1.1", last_commit=""):
    """把提取出来的 tasks 列表融合填充进规范的标准 YAML 模板"""
    tasks_yaml_lines = []
    for t in tasks:
        tasks_yaml_lines.append(f'    - id: "{t["id"]}"')
        tasks_yaml_lines.append(f'      name: "{t["name"]}"')
        tasks_yaml_lines.append('      source: "main"')
        tasks_yaml_lines.append('      language: "{mise_languages}"')
        tasks_yaml_lines.append(f'      command: "{t["command"]}"')
        tasks_yaml_lines.append(f'      default_cron: "{t["cron"]}"')
        tasks_yaml_lines.append(f'      enabled: {"true" if t["enabled"] else "false"}')
        tasks_yaml_lines.append('')

    tasks_yaml_str = "\n".join(tasks_yaml_lines)

    minimal_presets = []
    standard_presets = []
    hardcore_presets = []

    for t in tasks:
        t_id = t["id"]
        # 佛系保级
        minimal_presets.append(f'        {t_id}:\n          enabled: {"true" if t_id == "daily" else "false"}')

        # 标准日常满收益
        is_standard = t_id in ("daily", "manga", "manga_privilege", "silver2_coin", "silver2coin", "vip_bigpoint", "vip_privilege", "charge")
        standard_presets.append(f'        {t_id}:\n          enabled: {"true" if is_standard else "false"}')

        # 全能极客
        if t_id == "live_lottery":
            hardcore_presets.append(f'        {t_id}:\n          enabled: true\n          cron: "0 */20 * * * *"')
        elif t_id in ("login", "test", "try_fix"):
            hardcore_presets.append(f'        {t_id}:\n          enabled: false')
        else:
            hardcore_presets.append(f'        {t_id}:\n          enabled: true')

    minimal_presets_str = "\n".join(minimal_presets)
    standard_presets_str = "\n".join(standard_presets)
    hardcore_presets_str = "\n".join(hardcore_presets)

    raw_template = """# ==============================================================================
# 白虎面板应用规范定义文件 (Baihu Application Specification)
# 应用名称: B站全自动化助手 (BiliBiliToolPro)
# 规范版本: v1
# 本文件由 apps/BiliBiliToolPro/build.py 自动构建生成 (请勿手动修改)
# ==============================================================================

spec_version: "v1"
id: "bilibili-tool-pro"
name: "B站全自动化助手 (BiliBiliToolPro)"
version: "@@BH_SLOT_VERSION@@"
author: "RayWangQvQ"
category: "福利签到"
last_commit: "@@BH_SLOT_LAST_COMMIT@@"
template:
  - tag: "BiliBiliToolPro"
  - mise_languages: "node@23"
description: "基于 .NET 8 的 B站多功能全自动任务工具，支持每日经验投币、大会员权益礼包领取、天选时刻抽奖、粉丝牌助手与多账号管理"
icon: "https://raw.githubusercontent.com/RayWangQvQ/BiliBiliToolPro/main/docs/images/logo.png"
homepage: "https://github.com/RayWangQvQ/BiliBiliToolPro"
build_opts:
  force_setup: true
  skip_setup: false
  skip_sync: false
schedule_opts:
  schedule: "0 0 8 * * *"
  random_range: 0
  timeout: 30
  retry_count: 0
  retry_interval: 0

# ==============================================================================
# 1. 脚本代码源列表 (Sources) —— 纯 Release 预编译模式，无需 clone 上游源码
# ==============================================================================
sources:
  - id: "main"
    source_type: "null"

# ==============================================================================
# 2. 原生 Shell 环境与依赖编排 (Setup) —— 极速拉取官方跨平台 Release 包
# ==============================================================================
setup:
  # [可选] 依赖快速探测：已就绪时毫秒级跳过安装
  check: "node -e \\"const fs=require('fs'), p=require('path'); const bin=p.join(process.env.APP_DIR||process.cwd(),'bin'); if(!fs.existsSync(p.join(bin,'Ray.BiliBiliTool.Console')) && !fs.existsSync(p.join(bin,'Ray.BiliBiliTool.Console.exe'))){process.exit(1)}\\""

  # [必填] 依赖安装命令：根据当前操作系统架构拉取对应的官方 Release zip 并解压到 bin 目录
  install: |
    node -e "
    const fs = require('fs');
    const path = require('path');
    const https = require('https');
    const http = require('http');
    const { execSync } = require('child_process');

    const appDir = process.env.APP_DIR || process.cwd();
    const binDir = path.join(appDir, 'bin');
    fs.mkdirSync(binDir, { recursive: true });

    let osName = process.platform === 'win32' ? 'win' : (process.platform === 'darwin' ? 'osx' : 'linux');
    let archName = process.arch === 'arm64' ? 'arm64' : (process.arch === 'arm' ? 'arm' : 'x64');

    const version = '@@BH_SLOT_VERSION@@';
    const tag = '@@BH_SLOT_TAG@@';
    const zipName = 'bilibili-tool-pro-v' + version + '-' + osName + '-' + archName + '.zip';
    const rawUrl = 'https://github.com/RayWangQvQ/BiliBiliToolPro/releases/download/' + tag + '/' + zipName;

    const mirrors = [
      'https://ghfast.top/' + rawUrl,
      'https://gh-proxy.com/' + rawUrl,
      'https://ghproxy.net/' + rawUrl,
      rawUrl
    ];

    const tempZip = path.join(binDir, 'temp_release.zip');

    function downloadFile(url) {
      return new Promise((resolve, reject) => {
        const client = url.startsWith('https') ? https : http;
        const req = client.get(url, { headers: { 'User-Agent': 'BaihuApp-Downloader' } }, (res) => {
          if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
            return resolve(downloadFile(res.headers.location));
          }
          if (res.statusCode !== 200) {
            return reject(new Error('HTTP status ' + res.statusCode));
          }
          const fileStream = fs.createWriteStream(tempZip);
          res.pipe(fileStream);
          fileStream.on('finish', () => {
            fileStream.close(() => resolve(true));
          });
        });
        req.on('error', reject);
        req.setTimeout(30000, () => { req.destroy(); reject(new Error('Timeout')); });
      });
    }

    async function main() {
      console.log('>> 正在匹配系统架构: ' + osName + '-' + archName + ', 下载 Release 产物: ' + zipName);
      let downloaded = false;
      for (const m of mirrors) {
        try {
          console.log('>> 尝试下载源: ' + m);
          await downloadFile(m);
          if (fs.existsSync(tempZip) && fs.statSync(tempZip).size > 1000) {
            downloaded = true;
            console.log('>> 下载成功，文件大小: ' + fs.statSync(tempZip).size + ' 字节');
            break;
          }
        } catch (e) {
          console.log('>> 下载失败: ' + e.message + '，尝试下一镜像...');
          if (fs.existsSync(tempZip)) fs.unlinkSync(tempZip);
        }
      }

      if (!downloaded) {
        console.error('>> 所有镜像源下载失败！');
        process.exit(1);
      }

      console.log('>> 正在解压 Release 包到 ' + binDir + '...');
      try {
        if (process.platform === 'win32') {
          execSync('tar -xf \\\"' + tempZip + '\\\" -C \\\"' + binDir + '\\\"', { stdio: 'inherit' });
        } else {
          try {
            execSync('unzip -o -q \\\"' + tempZip + '\\\" -d \\\"' + binDir + '\\\"', { stdio: 'inherit' });
          } catch (_) {
            execSync('tar -xf \\\"' + tempZip + '\\\" -C \\\"' + binDir + '\\\"', { stdio: 'inherit' });
          }
        }
      } catch (e) {
        console.error('>> 解压失败: ' + e.message);
        process.exit(1);
      } finally {
        if (fs.existsSync(tempZip)) fs.unlinkSync(tempZip);
      }

      const execFile = path.join(binDir, 'Ray.BiliBiliTool.Console');
      if (fs.existsSync(execFile)) {
        try { fs.chmodSync(execFile, 0o755); } catch (_) {}
      }

      console.log('>> BiliBiliToolPro 预编译包准备就绪！');
    }

    main().catch(err => {
      console.error('>> 部署异常: ' + err.message);
      process.exit(1);
    });
    "

  # [可选] 后置初始化命令：安装成功后自动执行
  post_install: |
    echo ">> 后置初始化准备就绪！"

  # [可选] 应用卸载清理
  uninstall: |
    node -e "['bin'].forEach(p => require('fs').rmSync((process.env.APP_DIR || process.cwd()) + '/' + p, {recursive: true, force: true}))"

# ==============================================================================
# 3. 环境变量声明契约 (Env Schema) —— 驱动前端自动化渲染交互式表单
# ==============================================================================
env_schema:
  - key: "Ray_BiliBiliCookies__0"
    label: "主账号凭证 (Cookie)"
    type: "string"
    required: true
    description: "登录 bilibili.com 后获取的 Cookie，包含 SESSDATA、bili_jct 等字段（亦可通过扫码登录任务自动注入）"
    placeholder: "SESSDATA=xxxx; bili_jct=yyyy; DedeUserID=zzzz;"

  - key: "Ray_DailyTaskConfig__NumberOfCoins"
    label: "每日投币数量"
    type: "select"
    required: false
    default: "5"
    options:
      - label: "不投币 (0枚)"
        value: "0"
      - label: "保底 (1枚)"
        value: "1"
      - label: "拿满经验 (5枚)"
        value: "5"

  - key: "Ray_DailyTaskConfig__SelectLike"
    label: "投币同时点赞"
    type: "boolean"
    default: true
    description: "投币成功后是否同时点赞视频"

  - key: "Ray_LiveLotteryTaskConfig__AutoSendDanmu"
    label: "天选抽奖自动发弹幕"
    type: "boolean"
    default: true
    description: "遇到弹幕抽奖时是否自动发送所需弹幕"

  - key: "BaihuConfig__Token"
    label: "白虎面板 API Token"
    type: "string"
    required: false
    description: "白虎面板 OpenAPI 访问令牌。配置后运行【扫码登录】任务即可自动持久化 Cookie 回白虎面板！"
    placeholder: "在白虎面板【系统设置】->【OpenAPI】中创建"

  - key: "BA_URL"
    label: "白虎面板访问地址"
    type: "string"
    required: false
    default: "http://localhost:8052"
    description: "白虎面板的内部或局域网访问地址，用于接收扫码登录成功的 Cookie 回调"

  - key: "Ray_PlatformType"
    label: "运行平台类型"
    type: "string"
    required: false
    default: "Baihu"
    description: "指定底层运行平台为 Baihu，完全复刻青龙/白虎原生调度行为，实现扫码登录后自动将 Cookie 同步保存回面板"

  - key: "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT"
    label: "精简容器兼容模式 (无ICU)"
    type: "boolean"
    default: true
    description: "解决精简容器/系统环境下缺失 libicu 导致的初始化问题"

# ==============================================================================
# 4. 任务生成与映射规则 (Sync Rules) —— 规则独立热更新，无须上游仓库 Git Push
# ==============================================================================
sync_rules:
  # 全局任务默认参数
  defaults:
    timeout: 30                       # 默认超时（分钟）
    retry_count: 1                    # 失败重试次数
    retry_interval: 15                # 失败重试间隔（秒）
    work_dir: "{app_dir}/bin"         # 运行已解压的产物目录，实现 0.1 秒极速启动
    language: "{mise_languages}"      # 执行环境锁定为 {mise_languages}

  # 任务清单定义（解耦上游注释，标准化任务编排）
  tasks:
@@BH_SLOT_TASKS_YAML@@
# ==============================================================================
# 5. 使用场景模板 (Scenarios) —— 赋能用户一键选配，杜绝盲目生成冗余任务
# ==============================================================================
scenarios:
  - id: "minimal"
    name: "佛系保级模式"
    description: "仅执行每日登录与基础签到，耗时极短且完全防风控，适合只需保级的账号"
    default: false
    task_presets:
@@BH_SLOT_MINIMAL_PRESETS@@

  - id: "standard"
    name: "标准日常满收益模式 (推荐)"
    description: "开启每日签到、自动投币、大会员大积分与漫画权益领取，最大化每日经验与收益"
    default: true
    task_presets:
@@BH_SLOT_STANDARD_PRESETS@@

  - id: "hardcore"
    name: "全天候极客全能模式"
    description: "开启全部自动化功能，包括每 15 分钟一次的高频直播间天选时刻自动巡检抽奖"
    task_presets:
@@BH_SLOT_HARDCORE_PRESETS@@
"""

    slots = {
        "@@BH_SLOT_VERSION@@": version,
        "@@BH_SLOT_TAG@@": source_ref,
        "@@BH_SLOT_LAST_COMMIT@@": last_commit,
        "@@BH_SLOT_TASKS_YAML@@": tasks_yaml_str,
        "@@BH_SLOT_MINIMAL_PRESETS@@": minimal_presets_str,
        "@@BH_SLOT_STANDARD_PRESETS@@": standard_presets_str,
        "@@BH_SLOT_HARDCORE_PRESETS@@": hardcore_presets_str,
    }

    result = raw_template
    for slot, val in slots.items():
        result = result.replace(slot, val)

    # 严格校验：确保无任何遗漏插槽
    if "@@BH_SLOT_" in result:
        unfilled = re.findall(r"@@BH_SLOT_[A-Z_]+@@", result)
        raise ValueError(f"检测到未填充的模板插槽: {unfilled}")

    return result


def main():
    parser = argparse.ArgumentParser(description="BiliBiliToolPro app.yaml Manifest 自动构建器")
    parser.add_argument("-s", "--source-dir", help="可选：本地已有源码目录（留空则自动从 GitHub 浅克隆）")
    parser.add_argument("-o", "--output", help="生成的 app.yaml 输出路径", default="app.yaml")
    parser.add_argument("-p", "--proxy", help="克隆 GitHub 代理前缀 (例如 https://gh-proxy.com/)", default="")
    args = parser.parse_args()

    print("==================================================")
    print("白虎应用商店 - BiliBiliToolPro 构建流水线")
    print("==================================================")

    tmp_dir_handle = None
    repo_dir = None
    proxy = args.proxy or os.environ.get("GH_PROXY", "")

    # 1. 尝试从上游 GitHub Release 获取最新发布版本信息
    print(f"[版本] 正在检测上游最新 Release 信息...")
    release_info = fetch_latest_release_info(proxy)
    latest_version = release_info.get("version", "4.1.1")
    latest_tag = release_info.get("tag", latest_version)
    published_at = release_info.get("published_at", "")
    print(f"[版本] 上游最新 Release 版本: {latest_version} (Tag: {latest_tag})")

    if args.source_dir and Path(args.source_dir).exists():
        repo_dir = Path(args.source_dir).resolve()
        print(f"[源目录] 使用指定的本地目录: {repo_dir}")
    else:
        # 优先按最新 Release Tag 进行克隆，若失败则回退至 UPSTREAM_BRANCH
        tmp_dir_handle = clone_upstream_repo(proxy, branch_or_tag=latest_tag)
        if not tmp_dir_handle and latest_tag != UPSTREAM_BRANCH:
            print(f"[回退] 尝试从分支 {UPSTREAM_BRANCH} 克隆...")
            tmp_dir_handle = clone_upstream_repo(proxy, branch_or_tag=UPSTREAM_BRANCH)
        if tmp_dir_handle:
            repo_dir = Path(tmp_dir_handle.name)

    try:
        # 优先读取仓库内的 props 版本确认，若没有则使用 Release 版本
        actual_version = get_repo_version(repo_dir, fallback_version=latest_version)

        if repo_dir:
            print(f"[扫描] 正在解析 baihu/qinglong 任务配置...")
            tasks = parse_tasks_from_repo(repo_dir)
            print(f"[发现] 共提取出 {len(tasks)} 个有效任务配置:")
            for t in tasks:
                status = "默认启用" if t["enabled"] else "默认关闭"
                print(f"  - [{t['target_code']:<16}] {t['name']:<22} (Cron: {t['cron']:<14}, {status})")
        else:
            print("[警告] 无法拉取上游仓库，使用内置标准任务模板兜底生成。")
            tasks = parse_tasks_from_repo(Path("."))

        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = Path(__file__).resolve().parent / output_path

        print(f"\n[生成] 正在组装白虎规范应用配置清单 (v1)...")
        last_commit = get_repo_last_commit_time(repo_dir) or published_at
        yaml_content = generate_app_yaml(
            tasks,
            version=actual_version,
            source_ref=latest_tag,
            last_commit=last_commit
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml_content, encoding="utf-8")
        print(f"[完成] 已成功构建并写入: {output_path}")
        print(f"       文件大小: {output_path.stat().st_size} 字节")
    finally:
        if tmp_dir_handle:
            print(f"[清理] 正在清理临时工作区: {tmp_dir_handle.name}...")
            tmp_dir_handle.cleanup()

    print("==================================================")


if __name__ == "__main__":
    main()

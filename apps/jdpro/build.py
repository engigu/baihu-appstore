#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
白虎应用商店 - JDPro (6dylan6/jdpro) 动态声明式构建器
------------------------------------------------------------
作用:
  从上游开源仓库 (https://github.com/6dylan6/jdpro.git)
  拉取并自动动态扫描提取 JS/PY 脚本中的任务名称 (new Env) 与 Cron 定时规则，
  自动构建生成符合白虎应用规范 (Baihu App Specification v1) 的 app.yaml。

使用方式:
  python build.py [--source-dir <路径>] [--output <路径>] [--proxy <代理前缀>]
"""

import os
import sys
import re
import yaml
import tempfile
import argparse
import subprocess
from pathlib import Path

def multiline_str_representer(dumper, data):
    if '\n' in data:
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)

yaml.add_representer(str, multiline_str_representer)

UPSTREAM_REPO = "https://github.com/6dylan6/jdpro.git"
UPSTREAM_BRANCH = "main"

# 需要过滤的非任务公共辅助库脚本
EXCLUDE_FILES = {
    "sendNotify.js", "sendNotify.py", "jdCookie.js",
    "JS_USER_AGENTS.js", "USER_AGENTS.js", "JDSignValidator.js",
    "JDJRValidator_Pure.js", "jd_pullfix.py", "jd_indeps.js"
}

def clone_upstream_repo(proxy: str = "") -> tempfile.TemporaryDirectory:
    """克隆上游仓库到临时目录（深度为 1 浅克隆，支持镜像加速）"""
    proxies_to_try = [proxy] if proxy else ["", "https://ghproxy.net/", "https://ghp.ci/"]

    for p in proxies_to_try:
        tmp_dir = tempfile.TemporaryDirectory(prefix="baihu_jdpro_")
        repo_url = UPSTREAM_REPO
        if p:
            proxy_clean = p.rstrip("/") + "/"
            repo_url = f"{proxy_clean}{UPSTREAM_REPO}"

        print(f"[克隆] 正在尝试拉取上游 JDPro 仓库: {repo_url} (分支: {UPSTREAM_BRANCH})...")
        cmd = [
            "git", "clone",
            "--depth", "1",
            "--branch", UPSTREAM_BRANCH,
            repo_url,
            tmp_dir.name
        ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"[成功] 上游仓库已成功拉取至临时目录: {tmp_dir.name}")
            return tmp_dir
        else:
            err_msg = res.stderr.strip().splitlines()[-1] if res.stderr.strip() else "网络异常"
            print(f"[警告] 当前地址拉取失败 ({err_msg})，尝试备用线路...")
            tmp_dir.cleanup()

    print("[错误] 所有克隆线路均失败，尝试使用本地临时缓存处理。", file=sys.stderr)
    return None


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


def parse_tasks_from_repo(repo_dir: Path):
    """动态扫描 jdpro 仓库中的所有 js / py 脚本文件，解析提取任务与 Cron"""
    tasks = []
    
    script_files = sorted(list(repo_dir.glob("*.js")) + list(repo_dir.glob("*.py")))

    for s_file in script_files:
        filename = s_file.name
        if filename.startswith(".") or filename in EXCLUDE_FILES:
            continue

        content = ""
        for enc in ["utf-8", "gb18030", "gbk"]:
            try:
                content = s_file.read_text(encoding=enc)
                break
            except Exception:
                pass

        if not content:
            continue

        # 1. 动态提取 Env 任务名称
        name_m = re.search(r'new\s+Env\s*\(\s*[\'"](.*?)[\'"]\s*\)', content)
        if not name_m:
            name_m = re.search(r'[\'"]?name[\'"]?\s*:\s*[\'"](.*?)[\'"]', content)
        
        task_name = name_m.group(1).strip() if name_m else s_file.stem

        # 2. 动态提取 Cron 定时表达式
        cron_m = re.search(r'(?:cron|Cron)\s+[\'"]?([0-9\*\/\-\s]+)[\'"]?', content)
        cron = cron_m.group(1).strip() if cron_m else ""
        
        # 处理 5 位标准 Cron 补全为白虎 6 位 Cron（在前面加 0 秒）
        if cron:
            parts = cron.split()
            if len(parts) == 5:
                cron = "0 " + cron
        else:
            cron = "0 8 * * *"

        task_id = s_file.stem
        is_python = filename.endswith(".py")
        exec_cmd = f"mise exec {{mise_languages}} -- python main/6dylan6_jdpro/{filename}" if is_python else f"mise exec {{mise_languages}} -- node main/6dylan6_jdpro/{filename}"

        tasks.append({
            "id": task_id,
            "name": task_name,
            "source": "main",
            "command": exec_cmd,
            "schedule": cron,
            "remark": f"JDPro 动态任务：{task_name} ({filename})"
        })

    return tasks


def main():
    parser = argparse.ArgumentParser(description="JDPro 白虎应用构建器")
    parser.add_argument("--source-dir", default="", help="本地上游源码目录（提供时跳过 git clone）")
    parser.add_argument("--output", default="app.yaml", help="输出 app.yaml 相对路径")
    parser.add_argument("--proxy", default="", help="GitHub 加速代理前缀")
    args = parser.parse_args()

    tmp_dir_obj = None
    if args.source_dir and Path(args.source_dir).exists():
        repo_dir = Path(args.source_dir)
        print(f"[提示] 使用本地已有上游源码目录: {repo_dir}")
    else:
        # 优先检测本地已存在的源码缓存目录，防网络波动
        scratch_jd = Path(r"C:\Users\vm\.gemini\antigravity-ide\brain\2def54a6-d0ba-4d22-92da-e7fdec073048\scratch\jdpro")
        if scratch_jd.exists():
            repo_dir = scratch_jd
            print(f"[提示] 使用本地已知源码目录: {repo_dir}")
        else:
            tmp_dir_obj = clone_upstream_repo(args.proxy)
            if not tmp_dir_obj:
                sys.exit(1)
            repo_dir = Path(tmp_dir_obj.name)

    # 动态扫描提取任务
    scanned_tasks = parse_tasks_from_repo(repo_dir)
    print(f"[解析] 从上游仓库中动态解析提取到 {len(scanned_tasks)} 个脚本任务！")

    # 构建场景 Task 预设映射
    standard_enabled_keywords = ["变动", "CheckCK", "农场", "种豆", "庄园", "店铺", "签到", "收益"]
    
    standard_presets = {}
    minimal_presets = {}
    full_presets = {}

    for t in scanned_tasks:
        t_id = t["id"]
        t_name = t["name"]

        # 标准模式：匹配关键字
        is_std = any(k in t_name or k in t_id for k in standard_enabled_keywords)
        standard_presets[t_id] = {"enabled": is_std}

        # 极简模式：仅留变动和 CK 检测
        is_min = ("CheckCK" in t_id or "bean_change" in t_id or "变动" in t_name)
        minimal_presets[t_id] = {"enabled": is_min}

        # 全功能模式：全部启用
        full_presets[t_id] = {"enabled": True}

    last_commit = get_repo_last_commit_time(repo_dir)

    manifest = {
        "spec_version": "v1",
        "id": "jdpro",
        "name": "京东全功能自动化助手 (JDPro)",
        "version": "1.0.0",
        "author": "6dylan6",
        "category": "福利签到",
        "last_commit": last_commit,
        "template": [
            {"tag": "JDPro"},
            {"mise_languages": "node@20.18.0"}
        ],
        "description": f"基于 Node.js 的京东自动化全功能任务集合，动态包含 {len(scanned_tasks)} 个福利任务，支持资产变动通知、东东农场、汪汪庄园、店铺签到、签到提现等",
        "icon": "https://img10.360buyimg.com/img/jfs/t1/158580/38/20042/13936/6090f4e3E06b86cf0/64dd78b273d6b05e.png",
        "homepage": "https://github.com/6dylan6/jdpro",

        "sources": [
            {
                "id": "main",
                "source_type": "git",
                "source_url": "https://github.com/6dylan6/jdpro.git",
                "branch": "main",
                "path": "",
                "single_file": False,
                "proxy": "ghproxy",
                "target_path": "main"
            }
        ],

        "setup": {
            "check": "mise exec {mise_languages} -- node -e \"if (!process.version.startsWith('v20')) process.exit(1)\"",
            "install": (
                "mise install {mise_languages}\n"
                "echo \">> 正在为 JDPro 安装 Node.js 依赖...\"\n"
                "cd \"{app_dir}/main/6dylan6_jdpro\" && mise exec {mise_languages} -- npm install --no-audit --no-fund --production\n"
                "echo \">> JDPro 依赖就绪！\""
            ),
            "uninstall": "mise exec {mise_languages} -- node -e \"try{require('fs').rmSync('{app_dir}/main/6dylan6_jdpro/node_modules',{recursive:true,force:true})}catch(e){}\""
        },

        "env_schema": [
            {
                "key": "JD_COOKIE",
                "label": "京东账号凭证 (Cookie)",
                "type": "secret",
                "tag": "{tag}",
                "required": True,
                "description": "京东账号 Pt_Key 与 Pt_Pin 凭证，格式为 pt_key=xxx;pt_pin=yyy;（多账号可用 & 分隔）",
                "placeholder": "pt_key=AAJxxx; pt_pin=jd_123456;"
            },
            {
                "key": "PUSH_KEY",
                "label": "Server酱 PUSH_KEY",
                "type": "secret",
                "tag": "{tag}",
                "required": False,
                "description": "Server酱微信推送 Key，用于接收资产变动与通知"
            },
            {
                "key": "BARK_PUSH",
                "label": "Bark 推送地址",
                "type": "string",
                "tag": "{tag}",
                "required": False,
                "description": "iOS Bark 推送服务地址/Key"
            },
            {
                "key": "QYWX_AM",
                "label": "企业微信应用推送",
                "type": "secret",
                "tag": "{tag}",
                "required": False,
                "description": "企业微信应用消息推送参数"
            },
            {
                "key": "TG_BOT_TOKEN",
                "label": "Telegram Bot Token",
                "type": "secret",
                "tag": "{tag}",
                "required": False,
                "description": "Telegram 机器人 Token"
            },
            {
                "key": "TG_USER_ID",
                "label": "Telegram User ID",
                "type": "string",
                "tag": "{tag}",
                "required": False,
                "description": "Telegram 用户 ID"
            }
        ],

        "tasks": scanned_tasks,

        "scenarios": [
            {
                "id": "standard",
                "name": "标准运行模式",
                "default": True,
                "description": "智能精选日常资产变动通知、Cookie检测、农场、种豆与签到任务",
                "task_presets": standard_presets
            },
            {
                "id": "minimal",
                "name": "极简节能模式",
                "description": "仅保留 Cookie 状态检测与资产变动通知，省电低性能损耗",
                "task_presets": minimal_presets
            },
            {
                "id": "full",
                "name": "全功能完整模式",
                "description": "自动全量开启上游解析到的全部任务",
                "task_presets": full_presets
            }
        ]
    }

    output_path = (Path(__file__).resolve().parent / args.output).resolve()
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(manifest, f, allow_unicode=True, sort_keys=False)

    print(f"[成功] JDPro app.yaml 文件已顺利动态构建完成 -> {output_path} (包含 {len(scanned_tasks)} 个任务)")

    if tmp_dir_obj:
        tmp_dir_obj.cleanup()

if __name__ == "__main__":
    main()

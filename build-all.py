#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
白虎应用商店 - 全量应用构建调度器 (Global AppStore Builder)
------------------------------------------------------------------
作用:
  1. 自动扫描 apps/ 下的所有应用目录 (自动忽略 web, docs, static 等前端或辅助目录)；
  2. 发现 build.json 时，自动调度对应的构建器（支持 Python、Node.js、Shell 等任意语言）；
  3. 验证构建产物 app.yaml；
  4. 自动扫描所有 app.yaml 并聚合生成包含任务、场景与环境变量的富文本全商店索引 apps.json。

使用方式:
  python build-all.py [--apps-dir apps] [--proxy <代理前缀>]
"""

import os
import re
import sys
import json
import time
import shutil
import argparse
import subprocess
from pathlib import Path


def parse_yaml_metadata(yaml_path: Path) -> dict:
    """提取 app.yaml 中的元数据、任务、场景与环境变量契约"""
    meta = {}
    try:
        content = yaml_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"[警告] 读取 {yaml_path} 失败: {e}", file=sys.stderr)
        return meta

    # 基本信息
    for key in ["spec_version", "id", "name", "version", "author", "category", "description", "icon", "homepage"]:
        pattern = r'^' + key + r':\s*["\']?([^"\'\r\n]+)["\']?'
        m = re.search(pattern, content, re.MULTILINE)
        if m:
            meta[key] = m.group(1).strip()

    # 提取任务清单
    tasks_list = []
    tasks_match = re.search(r'tasks:\s*\n(.*?)(?=\n[a-z_]+:|\Z)', content, re.DOTALL)
    if tasks_match:
        raw_tasks = re.split(r'\n\s*-\s*id:\s*', "\n" + tasks_match.group(1))
        for rt in raw_tasks:
            if not rt.strip():
                continue
            lines = rt.strip().splitlines()
            t_id = lines[0].strip().strip('"\'')
            t_name = re.search(r'name:\s*["\']?([^"\'\r\n]+)["\']?', rt)
            t_cron = re.search(r'default_cron:\s*["\']?([^"\'\r\n]+)["\']?', rt)
            t_cmd = re.search(r'command:\s*["\']?([^"\'\r\n]+)["\']?', rt)
            t_enabled = re.search(r'enabled:\s*(true|false)', rt)
            tasks_list.append({
                "id": t_id,
                "name": t_name.group(1).strip() if t_name else t_id,
                "cron": t_cron.group(1).strip() if t_cron else "",
                "command": t_cmd.group(1).strip() if t_cmd else "",
                "enabled": (t_enabled.group(1).lower() == "true") if t_enabled else True
            })

    meta["tasks"] = tasks_list
    meta["tasks_count"] = len(tasks_list)

    # 提取环境变量契约
    env_list = []
    env_match = re.search(r'env_schema:\s*\n(.*?)(?=\n[a-z_]+:|\Z)', content, re.DOTALL)
    if env_match:
        raw_envs = re.split(r'\n\s*-\s*key:\s*', "\n" + env_match.group(1))
        for re_item in raw_envs:
            if not re_item.strip():
                continue
            lines = re_item.strip().splitlines()
            e_key = lines[0].strip().strip('"\'')
            e_label = re.search(r'label:\s*["\']?([^"\'\r\n]+)["\']?', re_item)
            e_type = re.search(r'type:\s*["\']?([^"\'\r\n]+)["\']?', re_item)
            e_tag = re.search(r'tag:\s*["\']?([^"\'\r\n]+)["\']?', re_item)
            e_req = re.search(r'required:\s*(true|false)', re_item)
            e_desc = re.search(r'description:\s*["\']?([^"\'\r\n]+)["\']?', re_item)
            e_def = re.search(r'default:\s*["\']?([^"\'\r\n]+)["\']?', re_item)
            env_list.append({
                "key": e_key,
                "label": e_label.group(1).strip() if e_label else e_key,
                "type": e_type.group(1).strip() if e_type else "string",
                "tag": e_tag.group(1).strip() if e_tag else "",
                "required": (e_req.group(1).lower() == "true") if e_req else False,
                "description": e_desc.group(1).strip() if e_desc else "",
                "default": e_def.group(1).strip() if e_def else ""
            })
    meta["env_schema"] = env_list

    # 提取场景预设
    scenarios_list = []
    sc_match = re.search(r'scenarios:\s*\n(.*)', content, re.DOTALL)
    if sc_match:
        raw_sc = re.split(r'\n\s*-\s*id:\s*', "\n" + sc_match.group(1))
        for rsc in raw_sc:
            if not rsc.strip():
                continue
            lines = rsc.strip().splitlines()
            s_id = lines[0].strip().strip('"\'')
            s_name = re.search(r'name:\s*["\']?([^"\'\r\n]+)["\']?', rsc)
            s_desc = re.search(r'description:\s*["\']?([^"\'\r\n]+)["\']?', rsc)
            s_def = re.search(r'default:\s*(true|false)', rsc)
            scenarios_list.append({
                "id": s_id,
                "name": s_name.group(1).strip() if s_name else s_id,
                "description": s_desc.group(1).strip() if s_desc else "",
                "default": (s_def.group(1).lower() == "true") if s_def else False
            })
    meta["scenarios"] = scenarios_list
    meta["scenarios_count"] = len(scenarios_list)

    return meta


def build_app(app_dir: Path, proxy: str = "") -> bool:
    """根据 app 目录下的 build.json 执行构建"""
    build_json_path = app_dir / "build.json"
    if not build_json_path.exists():
        print(f"[-] 跳过: {app_dir.name} 未定义 build.json (直接使用现有 app.yaml)")
        return True

    try:
        config = json.loads(build_json_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[错误] 解析 {build_json_path} 失败: {e}", file=sys.stderr)
        return False

    command_str = config.get("command")
    script = config.get("script")
    language = config.get("language", "").lower()
    output_file = config.get("output", "app.yaml")

    # 构建启动命令
    if command_str:
        cmd = command_str
    elif script:
        if language == "python":
            cmd = f"python {script}"
        elif language in ("node", "nodejs", "javascript"):
            cmd = f"node {script}"
        elif language in ("bash", "sh", "shell"):
            cmd = f"bash {script}"
        else:
            cmd = f"./{script}"
    else:
        print(f"[错误] {app_dir.name}/build.json 未指定 command 或 script", file=sys.stderr)
        return False

    if proxy:
        cmd += f" --proxy {proxy}"

    print(f"\n========================================================")
    print(f">> 正在构建应用: [{app_dir.name}]")
    print(f"   语言环境: {language or '系统命令'}")
    print(f"   执行命令: {cmd}")
    print(f"   目标产物: {output_file}")
    print(f"========================================================")

    start_time = time.time()
    res = subprocess.run(cmd, shell=True, cwd=str(app_dir))
    elapsed = time.time() - start_time

    target_path = app_dir / output_file
    if res.returncode != 0:
        print(f"[失败] 应用 [{app_dir.name}] 构建命令退出异常 (代码: {res.returncode}, 耗时: {elapsed:.2f}s)", file=sys.stderr)
        return False

    if not target_path.exists() or target_path.stat().st_size == 0:
        print(f"[失败] 应用 [{app_dir.name}] 未成功生成目标产物: {target_path}", file=sys.stderr)
        return False

    print(f"[成功] 应用 [{app_dir.name}] 构建完成! 产物大小: {target_path.stat().st_size} 字节, 耗时: {elapsed:.2f}s")
    return True


def main():
    parser = argparse.ArgumentParser(description="白虎应用商店全量构建调度器")
    parser.add_argument("--apps-dir", default="apps", help="应用存放根目录路径")
    parser.add_argument("--proxy", default="", help="GitHub 加速代理前缀 (可选)")
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parent
    apps_root = (root_dir / args.apps_dir).resolve()

    if not apps_root.exists():
        print(f"[错误] 应用目录不存在: {apps_root}", file=sys.stderr)
        sys.exit(1)

    print("########################################################")
    print("      白虎应用商店 (Baihu AppStore) 自动化构建调度")
    print("########################################################")
    print(f"应用目录: {apps_root}")
    print(f"代理加速: {args.proxy or '未开启'}\n")

    # 忽略 web, docs, static 等前端或展示目录
    app_dirs = [p for p in sorted(apps_root.iterdir()) if p.is_dir() and p.name not in ("web", "docs", "static") and not p.name.startswith(".")]
    if not app_dirs:
        print("[提示] apps 目录下暂无应用。")
        sys.exit(0)

    success_count = 0
    fail_count = 0
    apps_index = []

    # 1. 执行全部构建
    for app_dir in app_dirs:
        ok = build_app(app_dir, args.proxy)
        if ok:
            success_count += 1
        else:
            fail_count += 1

        # 2. 收集各应用的 app.yaml 信息
        yaml_candidates = [
            app_dir / "app.yaml",
            app_dir / "baihu-app.yaml",
        ]
        target_yaml = next((y for y in yaml_candidates if y.exists()), None)
        if target_yaml:
            meta = parse_yaml_metadata(target_yaml)
            meta["app_dir"] = app_dir.name
            meta["manifest_path"] = f"apps/{app_dir.name}/{target_yaml.name}"
            # 附带完整的 manifest_raw 清单内容与官方远程直链，供客户端零请求秒级部署
            try:
                meta["manifest_raw"] = target_yaml.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                meta["manifest_raw"] = ""
            meta["manifest_url"] = f"https://raw.githubusercontent.com/engigu/baihu-appstore/main/apps/{app_dir.name}/{target_yaml.name}"
            meta["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            apps_index.append(meta)

    # 3. 聚合输出 apps.json 全局索引
    index_data = {
        "version": "v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_apps": len(apps_index),
        "apps": apps_index,
    }

    index_file = root_dir / "apps.json"
    index_file.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n########################################################")
    print("                     构建总结报告")
    print("########################################################")
    print(f"  - 扫描应用数: {len(app_dirs)}")
    print(f"  - 构建成功数: {success_count}")
    print(f"  - 构建失败数: {fail_count}")
    print(f"  - 索引已生成: {index_file} ({len(apps_index)} 个应用入库)")
    print("########################################################\n")

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

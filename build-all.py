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

try:
    import yaml
except ImportError:
    print("[错误] 未检测到 pyyaml 依赖，请运行: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def parse_yaml_metadata(yaml_path: Path) -> dict:
    """提取 app.yaml 中的元数据、任务、场景与环境变量契约 (纯粹使用 PyYAML 标准解析)"""
    meta = {}
    try:
        content = yaml_path.read_text(encoding="utf-8", errors="ignore")
        doc = yaml.safe_load(content) or {}
    except Exception as e:
        print(f"[警告] 读取或解析 {yaml_path} 失败: {e}", file=sys.stderr)
        return meta

    if isinstance(doc, dict):
        # 基础元数据收集
        for key in ["spec_version", "id", "name", "version", "author", "category", "last_commit", "description", "icon", "homepage", "build_opts", "schedule", "schedule_opts", "template", "languages"]:
            if key in doc and doc[key] is not None:
                meta[key] = doc[key]

        # 纯收集合并，不进行多余的数据转换与正则篡改
        tasks = doc.get("tasks") or (doc.get("sync_rules") or {}).get("tasks") or []
        meta["tasks"] = tasks
        meta["tasks_count"] = len(tasks)
        meta["env_schema"] = doc.get("env_schema") or []
        scenarios = doc.get("scenarios") or []
        meta["scenarios"] = scenarios
        meta["scenarios_count"] = len(scenarios)

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
    py_bin = f'"{sys.executable}"' if sys.executable else "python"
    if command_str:
        if command_str.startswith("python3 "):
            cmd = f"{py_bin} {command_str[8:]}"
        elif command_str.startswith("python "):
            cmd = f"{py_bin} {command_str[7:]}"
        else:
            cmd = command_str
    elif script:
        if language == "python":
            cmd = f"{py_bin} {script}"
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
            # 附带原汁原味的完整 manifest_raw 清单文本与官方远程直链
            try:
                raw_text = target_yaml.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                raw_text = ""
            meta["manifest_raw"] = raw_text
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

    # 4. 向 jsDelivr 发起 Purge 刷新全球 CDN 缓存请求
    try:
        import urllib.request
        purge_url = "https://purge.jsdelivr.net/gh/engigu/baihu-appstore@main/apps.json"
        req = urllib.request.Request(purge_url, headers={"User-Agent": "BaihuAppStoreBuilder/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                print(f"[CDN Purge] 已成功向 jsDelivr 发送全球 CDN 缓存强刷请求!")
    except Exception as e:
        print(f"[CDN Purge 提示] jsDelivr 缓存刷新请求跳过/超时: {e}")

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

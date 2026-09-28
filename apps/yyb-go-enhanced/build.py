#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
白虎应用商店 - YYB-Go-Enhanced 声明式应用构建器 (Manifest Builder)
------------------------------------------------------------
作用:
  从上游开源仓库 (https://github.com/525815266/YYB-Go-Enhanced.git)
  获取最新版本、Commit 时间与元数据，动态构建符合白虎应用规范 (Baihu App Specification v1)
  且具备常驻服务 (service_opts) 属性的 app.yaml。
"""

import os
import sys
import argparse
import subprocess
import tempfile
from pathlib import Path

UPSTREAM_REPO = "https://github.com/525815266/YYB-Go-Enhanced.git"
UPSTREAM_BRANCH = "main"


def clone_upstream_repo(proxy: str = "") -> tempfile.TemporaryDirectory:
    """浅克隆上游仓库到临时目录"""
    proxies_to_try = [proxy] if proxy else ["", "https://gh-proxy.com/", "https://ghfast.top/"]

    for p in proxies_to_try:
        tmp_dir = tempfile.TemporaryDirectory(prefix="baihu_yyb_")
        repo_url = UPSTREAM_REPO
        if p:
            proxy_clean = p.rstrip("/") + "/"
            repo_url = f"{proxy_clean}{UPSTREAM_REPO}"

        print(f"[克隆] 尝试拉取上游仓库: {repo_url} (分支: {UPSTREAM_BRANCH})...")
        cmd = ["git", "clone", "--depth", "1", "--branch", UPSTREAM_BRANCH, repo_url, tmp_dir.name]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"[成功] 上游仓库已成功拉取至: {tmp_dir.name}")
            return tmp_dir
        else:
            tmp_dir.cleanup()

    print("[错误] 所有远程克隆均失败。", file=sys.stderr)
    return None


def get_repo_version(repo_dir: Path) -> str:
    """从 VERSION 文件读取版本号"""
    if repo_dir:
        v_file = repo_dir / "VERSION"
        if v_file.exists():
            try:
                v = v_file.read_text(encoding="utf-8").strip()
                if v:
                    return v
            except Exception:
                pass
    return "0.2.14"


def get_repo_last_commit_time(repo_dir: Path) -> str:
    """获取 git 仓库最近一次 commit 时间 (ISO 8601)"""
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


def generate_app_yaml(version: str, last_commit: str) -> str:
    if not last_commit:
        last_commit = "2026-09-28T14:39:36+08:00"

    yaml_content = f'''# ==============================================================================
# 白虎面板应用规范定义文件 (Baihu Application Specification)
# 应用名称: YYB-Go-Enhanced 账号与协议管理终端
# 规范版本: v1
# 本文件由 apps/yyb-go-enhanced/build.py 自动构建生成 (请勿手动修改)
# ==============================================================================

spec_version: "v1"
id: yyb-go-enhanced
name: YYB-Go-Enhanced 账号与协议管理终端
version: "{version}"
author: "525815266"
category: "系统工具"
last_commit: "{last_commit}"
template:
  - tag: "YYBGo"
  - mise_languages: "node@23.11.1"
description: "基于 Golang 与 Gin 架构的高性能 YYB 协议管理终端，提供微信多账号扫码登录、生命周期自愈保活、健康状态探测、以及青龙/带带/Arcadia 多面板变量自动同步。"
icon: "https://raw.githubusercontent.com/525815266/YYB-Go-Enhanced/main/resource/static/favicon.ico"
homepage: "https://github.com/525815266/YYB-Go-Enhanced"
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
service_opts:
  port: 38180
  health_path: /health
  auto_restart: true
  web_path: /
sources:
  - id: main
    source_type: git
    source_url: https://github.com/525815266/YYB-Go-Enhanced.git
    branch: main
    target_path: main
setup:
  check: mise exec {{mise_languages}} -- node -e "const fs=require('fs');const p=require('path');const d=process.env.APP_DIR||process.cwd();process.exit(fs.existsSync(p.join(d,'main','yyb-go'))||fs.existsSync(p.join(d,'main','yyb-go.exe'))?0:1)"
  install: |-
    echo ">> 正在从 GitHub Release 极速拉取对应架构的 YYB-Go 预编译二进制..."
    mise exec {{mise_languages}} -- node -e "
      const fs = require('fs');
      const path = require('path');
      const appDir = process.env.APP_DIR || process.cwd();
      const mainDir = path.join(appDir, 'main');
      if (!fs.existsSync(mainDir)) fs.mkdirSync(mainDir, {{ recursive: true }});

      const isWin = process.platform === 'win32';
      const isDarwin = process.platform === 'darwin';
      const arch = process.arch === 'arm64' ? 'arm64' : 'amd64';
      
      let platformTag = 'linux-' + arch;
      let targetName = 'yyb-go';
      if (isWin) {{
        platformTag = 'windows-amd64.exe';
        targetName = 'yyb-go.exe';
      }} else if (isDarwin) {{
        platformTag = 'darwin-' + arch;
      }}
      
      const fileName = 'yyb-go-' + platformTag;
      const targetPath = path.join(mainDir, targetName);
      console.log('>> 匹配架构: ' + process.platform + ' / ' + process.arch + ' -> ' + fileName);

      const rawUrl = 'https://github.com/engigu/baihu-appstore/releases/download/yyb-go-prebuilt/' + fileName;
      const mirrors = [
        'https://ghfast.top/' + rawUrl,
        'https://gh-proxy.com/' + rawUrl,
        'https://mirror.ghproxy.com/' + rawUrl,
        'https://ghproxy.net/' + rawUrl,
        'https://ghp.ci/' + rawUrl,
        rawUrl
      ];

      const tryDownload = (index) => {{
        if (index >= mirrors.length) {{
          console.error('>> [错误] 所有 Release 预编译加速源均拉取失败，请检查网络连通性');
          process.exit(1);
        }}
        const currentUrl = mirrors[index];
        console.log('>> 尝试镜像节点 (' + (index + 1) + '/' + mirrors.length + '): ' + currentUrl);
        let isHandled = false;
        const next = () => {{
          if (isHandled) return;
          isHandled = true;
          try {{ fs.unlinkSync(targetPath); }} catch(e){{}}
          tryDownload(index + 1);
        }};
        const fetchUrl = (reqUrl) => {{
          const client = reqUrl.startsWith('https') ? require('https') : require('http');
          const file = fs.createWriteStream(targetPath);
          const req = client.get(reqUrl, (res) => {{
            if (res.statusCode === 301 || res.statusCode === 302) {{
              file.close();
              const redirectUrl = new URL(res.headers.location, reqUrl).href;
              fetchUrl(redirectUrl);
            }} else if (res.statusCode === 200) {{
              res.pipe(file);
              file.on('finish', () => {{
                file.close();
                if (!isWin) {{ try {{ fs.chmodSync(targetPath, 0o755); }} catch(e){{}} }}
                else {{ try {{ fs.copyFileSync(targetPath, path.join(mainDir, 'yyb-go')); }} catch(e){{}} }}
                console.log('>> YYB-Go 原生二进制就绪:', targetName);
              }});
            }} else {{
              file.close();
              next();
            }}
          }});
          req.setTimeout(10000, () => {{
            console.warn('>> [超时] 当前节点响应较慢，自动切换下一镜像节点...');
            req.destroy();
            file.close();
            next();
          }});
          req.on('error', () => {{
            file.close();
            next();
          }});
        }};
        fetchUrl(currentUrl);
      }};

      tryDownload(0);
    "
    echo ">> YYB-Go-Enhanced 极速部署就绪！"
  uninstall: mise exec {{mise_languages}} -- node -e "const p=require('path');const d=process.env.APP_DIR||process.cwd();try{{require('fs').rmSync(p.join(d,'main'),{{recursive:true,force:true}})}}catch(e){{}}"
env_schema:
  - key: YYB_PORT
    label: 内部监听端口 (YYB_PORT)
    type: number
    required: false
    default: 38180
    description: YYB-Go 内部 Web 服务监听端口（缺省 38180，位于白虎保留端口池 38100~38900，白虎将自动分配反代）
    placeholder: "38180"
  - key: YYB_AUTH_DRIVER
    label: 网页控制台认证模式 (YYB_AUTH_DRIVER)
    type: select
    required: false
    default: sqlite
    options:
      - label: 内置 SQLite 账号体系 (默认)
        value: sqlite
      - label: 免密直达模式 (无需登录直接使用 Web 控制台)
        value: none
    description: Web 控制台认证驱动。选 sqlite 则需账号登录；选 none 则关闭密码校验，白虎反代直接进入免密工作台
  - key: YYB_ADMIN_USER
    label: 控制台管理员用户名 (YYB_ADMIN_USER)
    type: string
    required: false
    default: "admin"
    description: YYB-Go Web 控制台管理员用户名（默认 admin）
    placeholder: "admin"
  - key: YYB_ADMIN_PASSWORD
    label: 控制台管理员密码 (YYB_ADMIN_PASSWORD)
    type: secret
    required: false
    description: YYB-Go Web 控制台访问密码（留空则首个注册账号自动成为管理员）
    placeholder: "自定义管理员访问密码"
  - key: YYB_ENABLE_PC_LOGIN
    label: 开启本机微信快速授权 (Windows)
    type: boolean
    default: false
    description: 是否开启电脑端微信本地快速授权（开启后添加账号时可直接通过本机运行的微信确认，无需手机扫码）
  - key: YYB_PROTOCOL_TOKEN
    label: 外部协议调用鉴权令牌 (YYB_PROTOCOL_TOKEN)
    type: secret
    required: false
    description: 供白虎本地脚本或外部系统通过 HTTP 访问 /wx/* 协议接口时的 Bearer 鉴权 Token（留空则不开启访问限制）
    placeholder: "留空或输入自定义调用 Token"
tasks:
  - id: yyb_server
    name: YYB-Go 常驻后台服务与 Web 控制台
    source: main
    command: ./yyb-go -host 0.0.0.0 -port {{port}}
    work_dir: "{{app_dir}}/main"
    default_cron: "0 0 0 1 1 *"
    enabled: true
    service_opts:
      port: 38180
      health_path: /health
      auto_restart: true
      web_path: /
    remark: YYB-Go-Enhanced 核心常驻进程，提供微信账号扫码、健康探测与协议接口调试控制台
scenarios:
  - id: standard
    name: 标准常驻服务模式
    description: 默认启动 YYB-Go 核心常驻后台服务并开启 Web 智能反代控制台
    default: true
    task_presets:
      yyb_server:
        enabled: true
'''
    return yaml_content


def main():
    parser = argparse.ArgumentParser(description="YYB-Go-Enhanced app.yaml 构建器")
    parser.add_argument("-s", "--source-dir", help="本地源码目录路径")
    parser.add_argument("-o", "--output", default="app.yaml", help="输出路径")
    parser.add_argument("-p", "--proxy", default="", help="Git 克隆代理前缀")
    args = parser.parse_args()

    tmp_dir_handle = None
    repo_dir = None

    if args.source_dir and Path(args.source_dir).exists():
        repo_dir = Path(args.source_dir).resolve()
    elif not os.environ.get("GITHUB_ACTIONS") and Path("F:/workspace/YYB-Go-Enhanced").exists():
        repo_dir = Path("F:/workspace/YYB-Go-Enhanced").resolve()
    else:
        proxy = args.proxy or os.environ.get("GH_PROXY", "")
        tmp_dir_handle = clone_upstream_repo(proxy)
        if tmp_dir_handle:
            repo_dir = Path(tmp_dir_handle.name)

    try:
        version = get_repo_version(repo_dir)
        last_commit = get_repo_last_commit_time(repo_dir)
        content = generate_app_yaml(version, last_commit)

        out_path = Path(args.output)
        if not out_path.is_absolute():
            out_path = Path(__file__).resolve().parent / out_path

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        print(f"[完成] 已生成: {out_path}")
    finally:
        if tmp_dir_handle:
            tmp_dir_handle.cleanup()


if __name__ == "__main__":
    main()

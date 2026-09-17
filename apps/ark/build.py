#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
白虎应用商店 - Ark (duorameng/ark) 声明式构建器
------------------------------------------------------------
作用:
  根据 duorameng/ark 仓库生成符合白虎应用规范 (Baihu App Specification v1) 的 app.yaml。
"""

import os
import sys
import yaml
import argparse
import subprocess
from pathlib import Path

def multiline_str_representer(dumper, data):
    if '\n' in data:
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)

yaml.add_representer(str, multiline_str_representer)

def main():
    parser = argparse.ArgumentParser(description="Ark 应用构建器")
    parser.add_argument("--output", default="app.yaml", help="输出的 YAML 规范文件名")
    args = parser.parse_args()

    manifest = {
        "spec_version": "v1",
        "id": "ark",
        "name": "Ark 班轮货运管理终端",
        "version": "1.0.0",
        "author": "duorameng",
        "category": "系统工具",
        "last_commit": "2026-09-16T00:00:00+08:00",
        "template": [
            {"tag": "ark"},
            {"mise_languages": "node@23.11.1"}
        ],
        "description": "基于 OCI 标准协议与 Golang 独立单二进制的云端工作负载快照交付与分布式工作区同步系统，支持 AES-256 加密封条与极速分层增量直推。",
        "icon": "https://raw.githubusercontent.com/duorameng/ark/main/docs/images/logo.png",
        "homepage": "https://github.com/duorameng/ark",
        "build_opts": {
            "force_setup": True,
            "skip_setup": False,
            "skip_sync": False
        },
        "schedule_opts": {
            "schedule": "0 0 8 * * *",
            "random_range": 0,
            "timeout": 30,
            "retry_count": 0,
            "retry_interval": 0
        },

        "sources": [
            {
                "id": "main",
                "source_type": "null"
            }
        ],

        "setup": {
            "check": "mise exec {mise_languages} -- node -e \"const fs=require('fs');const d=process.env.APP_DIR||process.cwd();process.exit(fs.existsSync(require('path').join(d,'bin','ark'))||fs.existsSync(require('path').join(d,'bin','ark.exe'))?0:1)\"",
            "install": (
                "echo \">> 正在从 GitHub Release 下载 Ark 预编译二进制程序...\"\n"
                "mise exec {mise_languages} -- node -e \"\n"
                "  const fs = require('fs');\n"
                "  const path = require('path');\n"
                "  const appDir = process.env.APP_DIR || process.cwd();\n"
                "  const binDir = path.join(appDir, 'bin');\n"
                "  if (!fs.existsSync(binDir)) fs.mkdirSync(binDir, { recursive: true });\n\n"
                "  const isWin = process.platform === 'win32';\n"
                "  const targetName = isWin ? 'ark.exe' : 'ark';\n"
                "  const targetPath = path.join(binDir, targetName);\n"
                "  const platformTag = isWin ? 'windows-amd64.exe' : (process.platform === 'darwin' ? 'darwin-amd64' : 'linux-amd64');\n"
                "  const rawUrl = 'https://github.com/duorameng/ark/releases/latest/download/ark-' + platformTag;\n"
                "  const mirrors = [\n"
                "    'https://ghproxy.net/' + rawUrl,\n"
                "    'https://mirror.ghproxy.com/' + rawUrl,\n"
                "    'https://ghfast.top/' + rawUrl,\n"
                "    'https://ghproxy.com/' + rawUrl,\n"
                "    rawUrl\n"
                "  ];\n\n"
                "  const tryDownload = (index) => {\n"
                "    if (index >= mirrors.length) {\n"
                "      console.error('>> [错误] 所有加速源均下载失败，请检查网络连通性');\n"
                "      process.exit(1);\n"
                "    }\n"
                "    const currentUrl = mirrors[index];\n"
                "    const fetchUrl = (reqUrl) => {\n"
                "      const client = reqUrl.startsWith('https') ? require('https') : require('http');\n"
                "      const file = fs.createWriteStream(targetPath);\n"
                "      const req = client.get(reqUrl, (res) => {\n"
                "        if (res.statusCode === 301 || res.statusCode === 302) {\n"
                "          file.close();\n"
                "          const redirectUrl = new URL(res.headers.location, reqUrl).href;\n"
                "          fetchUrl(redirectUrl);\n"
                "        } else if (res.statusCode === 200) {\n"
                "          res.pipe(file);\n"
                "          file.on('finish', () => {\n"
                "            file.close();\n"
                "            if (!isWin) { try { fs.chmodSync(targetPath, 0o755); } catch(e){} }\n"
                "            console.log('>> Ark Release 二进制下载就绪:', targetName);\n"
                "          });\n"
                "        } else {\n"
                "          file.close();\n"
                "          try { fs.unlinkSync(targetPath); } catch(e){}\n"
                "          tryDownload(index + 1);\n"
                "        }\n"
                "      });\n"
                "      req.on('error', () => {\n"
                "        file.close();\n"
                "        try { fs.unlinkSync(targetPath); } catch(e){}\n"
                "        tryDownload(index + 1);\n"
                "      });\n"
                "    };\n"
                "    fetchUrl(currentUrl);\n"
                "  };\n"
                "  tryDownload(0);\n"
                "\"\n"
                "echo \">> Ark 部署完成！\""
            ),
            "uninstall": "mise exec {mise_languages} -- node -e \"const p=require('path');const d=process.env.APP_DIR||process.cwd();try{require('fs').rmSync(p.join(d,'bin'),{recursive:true,force:true})}catch(e){}\""
        },

        "env_schema": [
            {
                "key": "ARK_BACKUP_DIR",
                "label": "工作区源路径 (ARK_BACKUP_DIR)",
                "type": "string",
                "tag": "{tag}",
                "required": False,
                "default": "/root/workspace",
                "description": "需要备份与同步的工作区根目录路径（如 /root/workspace）",
                "placeholder": "/root/workspace"
            },
            {
                "key": "ARK_SEAL_KEY",
                "label": "AES-256 封条加密口令",
                "type": "string",
                "tag": "{tag}",
                "required": False,
                "default": "YourSecretKey",
                "description": "端到端 AES-256-CBC 封条自定义加密口令",
                "placeholder": "YourSecretKey"
            },
            {
                "key": "ARK_REGISTRY_TYPE",
                "label": "目标注册表通道 (ali/gh/both)",
                "type": "string",
                "tag": "{tag}",
                "required": False,
                "default": "gh",
                "description": "远端镜像注册表类型 (gh: GitHub Packages, ali: 阿里云 ACR, both: 双推)",
                "placeholder": "gh"
            },
            {
                "key": "ARK_REPOSITORY",
                "label": "目标镜像仓库路径",
                "type": "string",
                "tag": "{tag}",
                "required": False,
                "default": "ghcr.io/your-username/ark-backup",
                "description": "目标 OCI 镜像仓库全路径（如 ghcr.io/your-username/ark-backup）",
                "placeholder": "ghcr.io/your-username/ark-backup"
            }
        ],

        "tasks": [
            {
                "id": "ark_check",
                "name": "环境与密钥就绪自检",
                "source": "main",
                "tag": "{tag}",
                "command": "{app_dir}/bin/ark check",
                "default_cron": "0 0 8 * * *",
                "enabled": True,
                "remark": "自检权限、配置、密钥加密与网络连通闭环"
            },
            {
                "id": "ark_board",
                "name": "每日增量快照打包登船交付",
                "source": "main",
                "tag": "{tag}",
                "command": "{app_dir}/bin/ark board --day --auto-scan",
                "default_cron": "0 0 2 * * *",
                "enabled": True,
                "remark": "全自动探测变更，按天打标并分层增量推送至云端注册表"
            },
            {
                "id": "ark_dry",
                "name": "模拟演练与全量校验 (Dry Run)",
                "source": "main",
                "tag": "{tag}",
                "command": "{app_dir}/bin/ark dry",
                "default_cron": "0 0 12 * * *",
                "enabled": False,
                "remark": "模拟分层打包与冷热度排序验证，不产生真实网络推流"
            }
        ],

        "scenarios": [
            {
                "id": "standard",
                "name": "标准自动打包备份模式",
                "description": "启用每日定时快照登船交付与环境健康度自检",
                "default": True,
                "task_presets": {
                    "ark_check": {"enabled": True},
                    "ark_board": {"enabled": True},
                    "ark_dry": {"enabled": False}
                }
            },
            {
                "id": "minimal",
                "name": "仅环境自检模式",
                "description": "仅保留基础状态检测，挂起定时打包",
                "default": False,
                "task_presets": {
                    "ark_check": {"enabled": True},
                    "ark_board": {"enabled": False},
                    "ark_dry": {"enabled": False}
                }
            }
        ]
    }

    script_dir = Path(__file__).parent.resolve()
    out_path = script_dir / args.output

    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(manifest, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    print(f"[成功] 已成功构建 Ark 应用定义文件: {out_path}")

if __name__ == "__main__":
    main()

# 白虎应用商店 (Baihu AppStore)

[![Build and Deploy Apps Index](https://github.com/engigu/baihu-appstore/actions/workflows/build-apps.yml/badge.svg)](https://github.com/engigu/baihu-appstore/actions/workflows/build-apps.yml)
[![Baihu Specification](https://img.shields.io/badge/Specification-v1-blue.svg)](docs/guide/app-spec.md)

白虎应用商店是面向**白虎面板 (Baihu Panel)** 的声明式应用市场与生态中心。

不同于传统定时脚本平台的“纯代码仓库扫描”，白虎应用规范 (Baihu App Specification v1) 提出了**“声明式应用工程”**理念。应用不仅可以包含完整的运行时安装依赖、环境变量交互契约、预编译架构，还支持多任务场景（Scenario）一键选配与模板宏占位符机制。

---

## 目录

- [一、 仓库目录结构](#一-仓库目录结构)
- [二、 应用描述文件 (app.yaml) 结构规范](#二-应用描述文件-appyaml-结构规范)
  - [1. 基础元数据 (Metadata)](#1-基础元数据-metadata)
  - [2. 模板占位符定义 (Template)](#2-模板占位符定义-template)
  - [3. 代码源列表 (Sources)](#3-代码源列表-sources)
  - [4. 环境与依赖编排 (Setup)](#4-环境与依赖编排-setup)
  - [5. 环境变量与凭证契约 (Env Schema)](#5-环境变量与凭证契约-env-schema)
  - [6. 任务清单与调度映射 (Tasks / Sync Rules)](#6-任务清单与调度映射-tasks--sync-rules)
  - [7. 运行场景预设模板 (Scenarios)](#7-运行场景预设模板-scenarios)
- [三、 索引构建与全量索引 (apps.json)](#三-索引构建与全量索引-appsjson)
- [四、 贡献指南 (How to Contribute)](#四-贡献指南-how-to-contribute)
- [五、 版权与移除说明 (Notice & Opt-out Policy)](#五-版权与移除说明-notice--opt-out-policy)

---

## 一、 仓库目录结构

```text
baihu-appstore/
├── apps/                        # [核心] 应用定义根目录
│   ├── BiliBiliToolPro/        # [示例应用] B站全自动化助手
│   │   ├── app.yaml            # 应用主描述文件 (App Manifest)
│   │   ├── build.py            # [可选] 应用独有的自动化构建/同步脚本
│   │   └── build.json          # [可选] 构建任务声明
│   └── <your-app-id>/          # 新接入的应用目录
│       └── app.yaml
├── build-all.py                 # 全应用索引扫描与聚合脚本 (生成 apps.json)
├── apps.json                    # 全局应用索引表 (给白虎面板客户端拉取使用)
└── README.md                    # 本文档
```

---

## 二、 应用描述文件 (app.yaml) 结构规范

每个应用必须包含一个 `app.yaml` 或 `baihu-app.yaml` 文件。完整结构如下：

```yaml
# ==============================================================================
# 白虎面板应用规范定义文件 (Baihu Application Specification v1)
# 应用标识: my-app
# ==============================================================================

spec_version: "v1"                    # 规范版本号 (固定为 v1)
id: "my-app"                          # 全局唯一标识符（字母、数字、中划线）
name: "我的示例应用"                    # 应用显示名称
version: "1.0.0"                      # 应用语义化版本号
author: "Baihu Community"             # 作者或维护团队
category: "福利签到"                   # 分类 (福利签到 / 消息推送 / 工具脚本 / 运维管理 等)
last_commit: "2026-09-16T11:14:00Z"   # 上游代码/仓库最近 Git Commit 提交时间 (ISO 8601)
description: "这是一段关于该应用功能的详细说明..."
icon: "https://example.com/icon.png"  # 图标 URL
homepage: "https://github.com/..."    # 开源项目主页

# ------------------------------------------------------------------------------
# 0. 高级构建与部署控制预设 (Build Opts，可选)
# ------------------------------------------------------------------------------
# 预配置应用部署与构建行为的默认开关（用户在面板安装界面仍可自由临时勾选覆盖）
build_opts:
  force_setup: false                  # 强制重新编译 (Rebuild)：跳过探活断言，强行重新执行 setup.install
  skip_setup: false                   # 跳过环境与依赖安装：完全跳过 setup 阶段，仅同步环境变量与任务
  skip_sync: false                    # 跳过代码源同步：使用本地已有代码，不重新拉取 Git/URL 源码

# ------------------------------------------------------------------------------
# 0.1 应用主任务调度规则与策略预设 (Schedule / Schedule Opts，可选)
# ------------------------------------------------------------------------------
# 预配置应用主任务 (Master Task) 的默认定时与调度策略（用户在安装界面可自由调整覆盖，亦可不填）
# 支持简写形式 schedule: "0 0 8 * * *" 或结构化对象 schedule_opts:
schedule_opts:
  schedule: "0 0 8 * * *"             # 默认定时规则 Cron 表达式 (秒 分 时 日 月 周，必须 6 位)
  random_range: 0                     # 基准时间后随机延迟 (秒，0~N)
  timeout: 30                         # 执行超时时间 (分钟，默认30)
  retry_count: 0                      # 失败重试次数 (默认0)
  retry_interval: 0                   # 失败重试间隔 (秒，默认0)

# ------------------------------------------------------------------------------
# 1. 模板占位符与运行环境声明 (Template)
# ------------------------------------------------------------------------------
# 声明自定义宏变量，在当前 YAML 的 {tag}、{mise_languages} 等位置原样保留；
# 白虎面板 (Go 核心解析器) 在运行时会自动解析该节点，提取 mise_languages 作为应用运行环境并在 UI 中展示！
# 重要：mise_languages 只能使用空格分隔多个环境（严禁使用逗号，例如 "dotnet@8.0.425 node@23"）
template:
  - tag: "BiliBiliToolPro"
  - mise_languages: "dotnet@8.0.425 node@23"

# ------------------------------------------------------------------------------
# 2. 脚本代码源列表 (Sources)
# ------------------------------------------------------------------------------
# 定义上游源码仓库或单文件直链，支持配置多个源，100% 复用白虎 reposync 参数
# 注：对于仅拉取 Release 二进制产物或无上游源码的应用，source_type 可声明为 null / none，无需代码同步
sources:
  - id: "main"                        # 源唯一标识符
    source_type: "git"                # git (Git仓库) / url (单文件直链) / null (纯二进制免同步模式)
    source_url: "https://github.com/user/repo.git" # 源码地址 (source_type 为 null 时可省略)
    branch: "main"                    # 指定检出分支
    path: ""                          # 稀疏检出子目录 (留空为全量)
    single_file: false                # 是否为单文件模式
    proxy: "ghproxy"                  # 镜像代理 (none / ghproxy / mirror / custom)
    target_path: "main"               # 检出存储目录 (相对 sources/{id})

# ------------------------------------------------------------------------------
# 3. 原生 Shell 环境与依赖编排 (Setup)
# ------------------------------------------------------------------------------
# 需兼顾 Linux 与 Windows (PowerShell/CMD) 跨平台语法规范：
#  - 避免使用仅 Linux 支持的 `2>/dev/null`、`grep` 或 `rm -rf`；
#  - 推荐使用 Node/Python 原生脚本当做跨平台工具命令。
setup:
  # 依赖快速探测命令：退出码 0 表示已就绪秒级跳过；非 0 则进入安装
  check: "mise exec {mise_languages} -- node -e \"if (!process.version.startsWith('v23')) process.exit(1)\""

> [!TIP]
> **预装底座环境说明 (Docker Base Environments)**：
> 白虎面板系统镜像内已预装统一的标准运行环境及全局环境变量，编写应用 Manifest 时推荐优先复用：
> - **时区**: `TZ=Asia/Shanghai`
> - **Node.js**: `NODE_VERSION=23.11.1` (`node@23.11.1`)
> - **Python**: `PYTHON_VERSION=3.13.12` (`python@3.13.12`)
> - **Mise 目录**: `MISE_DATA_DIR=/opt/mise-base`, `MISE_CONFIG_DIR=/opt/mise-base`
> - **PATH**: `/opt/mise-base/shims:/opt/mise-base/bin:$PATH`
> 
> 在 `app.yaml` 的 `template` 节点配置 `mise_languages: "node@23.11.1"` 或 `python@3.13.12` 可直接调用镜像预装环境，实现 0.1 秒秒级启动与免在线重复安装。

  # 原生 Shell 安装脚本：安装依赖、拉取工具包或预编译产物
  install: |
    mise install {mise_languages}
    echo ">> 正在安装应用依赖..."
    cd "{{app_dir}}/main" && mise exec {mise_languages} -- npm install --no-audit --no-fund

  # [可选] 后置初始化命令：安装/构建成功后自动执行的后置 Shell 脚本
  post_install: |
    echo ">> 正在初始化配置文件..."

  # [可选] 应用卸载时的清理命令 (使用 Node.js fs.rmSync 零依赖跨平台清理)
  uninstall: "mise exec {mise_languages} -- node -e \"try{require('fs').rmSync('{{app_dir}}/main/node_modules',{recursive:true,force:true})}catch(e){}\""

# ------------------------------------------------------------------------------
# 4. 环境变量与凭证契约 (Env Schema)
# ------------------------------------------------------------------------------
# 驱动前端可视化自动渲染交互表单 (支持 string / secret / number / boolean / select)
env_schema:
  - key: "MY_APP_COOKIE"
    label: "账号 Cookie 凭证"
    type: "secret"                    # 密文输入框 (前端已做防浏览器自动填充处理)
    tag: "{tag}"                      # 绑定的 Tag 名称
    required: true
    description: "请输入抓包获得的包含 session 的 Cookie 字符串"
    placeholder: "session=xxxx;"

  - key: "COIN_COUNT"
    label: "每日投币数量"
    type: "select"                    # 下拉选择框
    tag: "{tag}"
    required: false
    default: "5"
    options:                          # 下拉选项列表
      - label: "不投币 (0枚)"
        value: "0"
      - label: "保底 (1枚)"
        value: "1"
      - label: "拿满经验 (5枚)"
        value: "5"

  - key: "AUTO_LIKE"
    label: "投币同时点赞"
    type: "boolean"                   # 开关 Switch 控件
    tag: "{tag}"
    default: true
    description: "投币成功后是否同时为视频点赞"

# ------------------------------------------------------------------------------
# 5. 任务生成与调度映射 (Sync Rules / Tasks)
# ------------------------------------------------------------------------------
sync_rules:
  defaults:
    timeout: 15                       # 默认超时时间 (分钟)
    retry_count: 1                    # 失败重试次数
    retry_interval: 10                # 重试间隔 (秒)
    work_dir: "{app_dir}/main"        # 任务运行时工作目录
    language: "{mise_languages}"      # 锁定运行时环境

  tasks:
    - id: "daily_task"
      name: "每日基础签到与任务"
      source: "main"
      tag: "{tag}"
      language: "{mise_languages}"
      command: "python3 daily.py"
      default_cron: "0 0 9 * * *"
      enabled: true

    - id: "lottery_task"
      name: "高频巡检抽奖"
      source: "main"
      tag: "{tag}"
      language: "{mise_languages}"
      command: "python3 lottery.py"
      default_cron: "*/15 * * * *"
      enabled: false

# ------------------------------------------------------------------------------
# 6. 使用场景模板 (Scenarios)
# ------------------------------------------------------------------------------
# 提供一键场景预设，控制不同模式下的任务启停与 Cron 覆盖
scenarios:
  - id: "standard"
    name: "日常推荐模式"
    description: "仅开启每日签到与投币，耗时极短，安全无风控"
    default: true
    task_presets:
      daily_task:
        enabled: true
      lottery_task:
        enabled: false

  - id: "hardcore"
    name: "极客全能模式"
    description: "开启包括高频抽奖在内的所有任务"
    task_presets:
      daily_task:
        enabled: true
      lottery_task:
        enabled: true
        cron: "0 */10 * * * *"
```

---

## 三、 索引构建与全量索引 (apps.json)

`build-all.py` 脚本担任应用商店的**静态汇总器 (Static Aggregator)** 角色：

* **简单收集合并**：自动遍历 `apps/` 目录下所有的 `app.yaml` 文件；
* **保持原汁原味**：不做任何多余的数据转换、清洗或模板替换，将 YAML 解析为 JSON 并打包合并为仓库根目录下的 `apps.json`；
* **CI/CD 自动化**：每次将更改 Push 到 `main` 分支时，GitHub Actions 会自动触发 `.github/workflows/build-apps.yml` 重新运行构建并更新 `apps.json`。

#### 本地测试构建命令：
```bash
mise x -- python build-all.py
```

---

## 四、 贡献指南 (How to Contribute)

欢迎广大开发者将优秀的自动化工具接入白虎应用商店！接入步骤如下：

1. **Fork 本仓库**；
2. 在 `apps/` 目录下新建以你的应用 ID 命名的文件夹（如 `apps/my-awesome-tool/`）；
3. 参考上述规范在该目录下创建 `app.yaml`；
4. 运行 `mise x -- python build-all.py` 确保构建通过且 `apps.json` 已正确包含你的应用；
5. 提交 **Pull Request** 到 `main` 分支。

---

## 五、 版权与移除说明 (Notice & Opt-out Policy)

白虎应用商店 (Baihu AppStore) 仅对开源/公开的自动化工具进行声明式配置与索引编排，所有源码版权归原上游仓库作者所有。

* **原作者移除请求**：如果您是开源仓库的原作者，不希望您的项目被白虎应用商店收录，欢迎提交 **Pull Request**（直接删除 `apps/<your-app-id>` 目录）或提交 **Issue** 进行说明，我们会在确认后第一时间合并 PR 或将其从应用商店全量索引中下架移除。

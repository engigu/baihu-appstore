---
trigger: always_on
---

# 白虎应用规范 (app.yaml) 构建与编写规范规则 (Build Note)

本文档根据 [README.md] 及实际白虎面板解析要求，提炼汇总了 `app.yaml`（Baihu App Specification v1）中每个节点的构建规范与编写要点。

---

## 一、 根节点与基础元数据 (Metadata)

每个应用必须包含一个 `app.yaml`（或 `baihu-app.yaml`），定义应用的全局基础信息：

- **`spec_version`**（必填）：规范版本，固定为 `"v1"`。
- **`id`**（必填）：全局唯一应用标识符，仅支持小写字母、数字及中划线 `-`（例如：`bilibili-tool-pro`、`jdpro`、`ark`）。
- **`name`**（必填）：UI 界面展示的应用名称。
- **`version`**（必填）：语义化版本号（例如：`1.0.0`、`2.1.0`）。
- **`author`**（必填）：上游开源项目作者或维护者标识。
- **`category`**（必填）：分类标签（如：`福利签到`、`系统工具`、`消息推送`、`运维管理`）。
- **`last_commit`**（必填）：上游仓库/代码的最近 Git Commit 时间戳，采用 ISO 8601 格式（例如：`2026-09-16T11:14:00Z`）。
- **`description`**（必填）：应用的详细功能介绍。
- **`icon`**（必填）：应用图标图片公网直链 URL。
- **`homepage`**（必填）：上游开源项目主页或 GitHub 仓库地址。
- **`build_opts`**（可选）：高级构建与部署控制预设开关：
  - `force_setup`：布尔值，是否默认强制重新编译（跳过 check 探活，强行执行 setup.install，默认 `false`）。
  - `skip_setup`：布尔值，是否默认跳过环境与依赖安装（完全跳过 setup 阶段，默认 `false`）。
  - `skip_sync`：布尔值，是否默认跳过代码源同步（使用本地已有代码，默认 `false`）。
- **`schedule` / `schedule_opts`**（可选）：应用主任务 (Master Task) 的默认定时规则与调度策略预设（安装界面默认填充，亦可不填）：
  - `schedule`：字符串，默认 Cron 定时表达式（6 位秒级标准 Cron，如 `0 0 8 * * *`）。
  - `schedule_opts`：对象结构，完整覆盖主任务调度策略：
    - `schedule`：默认 Cron 定时规则表达式（必须 6 位）。
    - `random_range`：基准时间后随机延迟范围（单位：秒）。
    - `timeout`：单次运行执行超时（单位：分钟，默认 30）。
    - `retry_count`：失败重试次数（默认 0）。
    - `retry_interval`：失败重试间隔（单位：秒，默认 0）。

---

## 二、 模板宏与占位符定义 (`template`)

用于声明宏变量，在 `app.yaml` 中以 `{变量名}`（如 `{tag}`、`{mise_languages}`、`{app_dir}`）形式保留，面板在运行时自动进行全局插值替换与语言契约解析：

- **格式**：键值对数组（列表），例如：
  ```yaml
  template:
    - tag: "BiliBiliToolPro"
    - mise_languages: "dotnet@8.0.425 node@23"
  ```
  *说明*：`mise_languages` 声明应用运行时所依附的多语言环境，**只能以空格分隔多个语言版本（严禁使用逗号，例如 `"dotnet@8.0.425 node@23"`）**。白虎面板在安装/解析 Manifest 时会自动提取并渲染至 UI 面板中供用户选择调整。
- **预装底座环境说明**：
  白虎面板系统镜像默认预装标准环境，推荐优先复用以实现秒级启动与免重复安装：
  - **Node.js**: `node@23.11.1`
  - **Python**: `python@3.13.12`
  - **.NET / Golang 等**: 指定特定版本（如 `dotnet@8.0.425`、`go@1.22.5`）。

---

## 三、 代码源列表 (`sources`)

定义上游源码仓库或文件直链，100% 复用白虎面板 `reposync` 规范：

- **`id`**（必填）：数据源唯一 ID，在后续 `tasks` 中通过 `source: "<id>"` 关联（如 `main`）。
- **`source_type`**（必填）：数据源类型：
  - `git`：Git 仓库代码同步。
  - `url`：单文件直接下载。
  - `null` / `none`：空源类型（适用于纯 Release 二进制产物或无需上游源码克隆的应用。白虎面板在安装时将直接跳过 `reposync` 阶段）。
- **`source_url`**：Git 仓库克隆地址或下载链接（`source_type` 为 `git` 或 `url` 时必填；为 `null`/`none` 时可省略）。
- **`branch`**：Git 分支名（默认 `main` 或 `master`）。
- **`path`**：稀疏检出子目录（留空为全量检出）。
- **`single_file`**：是否为单文件（布尔值，`false` / `true`）。
- **`proxy`**：代理通道，支持 `none`、`ghproxy`、`mirror`、`custom`。
- **`target_path`**：在应用源码目录下的存储相对路径（如 `main`）。

---

## 四、 原生 Shell 环境与依赖编排 (`setup`)

定义应用部署、环境检查与依赖准备流程。**核心要求：必须具备跨平台兼容性（Windows 与 Linux/macOS）**：

1. **`check`（可选）**：
   - 依赖与可执行产物毫秒级探测命令。
   - 退出码为 `0` 表示环境/文件就绪（跳过 `install`）；退出码非 `0` 则触发执行 `install`。
   - 跨平台写法推荐：使用 Node.js 探测对应平台文件是否存在，兼容 `.exe` 与无扩展名文件。
2. **`install`（必填）**：
   - 依赖安装、预编译或 Release 二进制拉取 Shell 脚本。
   - **跨平台严禁使用纯 Linux 命令**（严禁单独使用 `2>/dev/null`、`grep`、`uname -s`、`rm -rf` 等）。
   - **预编译程序直接拉取模式**：如果支持直接下载 Release 二进制，优先通过跨平台脚本（如 Node.js http/https）下载对应的操作系统架构产物，并配置多个国内加速镜像源容错轮询。在 Node.js 脚本中拼接路径时，推荐使用 `process.env.APP_DIR || process.cwd()`，避免 Windows 平台下反斜杠在字符串插值中被当作转义字符破坏路径。
   - **源码依赖/编译模式**：需调用 `mise install {mise_languages}` 确保语言环境，并通过 `mise exec {mise_languages} -- ...` 执行安装/构建命令。
3. **`post_install`（可选）**：
   - 安装或编译完成后自动执行的后置初始化 Shell 脚本。
4. **`uninstall`（可选）**：
   - 应用卸载时执行的清理操作，推荐使用 Node.js 的 `fs.rmSync` 进行跨平台安全清理。

---

## 五、 环境变量与凭证契约 (`env_schema`)

驱动白虎面板前端自动渲染可视化配置表单，并支持一键注入任务运行时环境变量：

- **`key`**（必填）：实际注入系统的环境变量名（如 `ARK_BACKUP_DIR`、`JD_COOKIE`）。
- **`label`**（必填）：前端表单显示的中文标题。
- **`type`**（必填）：字段控件类型：
  - `string`：常规文本输入框。
  - `secret`：敏感密钥输入框（带遮罩，防止浏览器自动填充）。
  - `boolean`：开关 Switch 控件。
  - `select`：下拉单选框（需提供 `options` 列表，包含 `label` 与 `value`）。
  - `number`：数字输入框。
- **`tag`**：绑定的应用标签，通常填写 `"{tag}"`。
- **`required`**：是否必填（`true` / `false`）。
- **`default`**：默认缺省值。
- **`description`**：字段用法说明与提示。
- **`placeholder`**：输入框占位提示符。

---

## 六、 任务编排与调度映射 (`tasks` / `sync_rules`)

定义应用被拆解为白虎面板可执行任务项的清单：

- **`tasks`**（列表）：
  - **`id`**（必填）：子任务内部 ID。
  - **`name`**（必填）：子任务中文显示名称。
  - **`source`**（必填）：关联的 `sources` 中的源 ID（通常为 `main`）。
  - **`command`**（必填）：具体执行的纯原生 CLI 命令（如 `dotnet Ray.BiliBiliTool.Console.dll` 或 `node main/jd_CheckCK.js`；**坚决不写 `mise exec` 前缀**，多语言外壳由白虎面板自动动态包裹）。
  - **`default_cron`**（必填）：默认 Cron 定时表达式（6 位或 5 位标准 Cron）。
  - **`enabled`**（必填）：默认是否启用（`true` / `false`）。
  - **`tag`**（可选）：关联标签，推荐统一填 `"{tag}"`，与环境变量保持一致归集。
  - **`remark`**：任务功能备注与执行说明。
- **`sync_rules.defaults`**（可选）：
  - `timeout`：默认执行超时时间（单位：分钟）。
  - `retry_count`：失败自动重试次数。
  - `retry_interval`：重试间隔（秒）。
  - `work_dir`：任务运行工作目录。
  - `language`：锁定运行时语言（如 `"{mise_languages}"`）。

---

## 七、 运行场景预设模板 (`scenarios`)

提供一键场景选配方案，控制不同模式下的子任务批量启停状态与定制 Cron：

- **`id`**（必填）：场景唯一标识（如 `standard`、`minimal`、`hardcore`）。
- **`name`**（必填）：场景显示名称（如 `日常标准模式`、`仅环境自检模式`）。
- **`description`**：场景用途说明。
- **`default`**：是否为默认选中场景（布尔值，仅一个场景为 `true`）。
- **`task_presets`**：以 `tasks[].id` 为键的字典对象，控制每个子任务的启停与定制规则：
  ```yaml
  task_presets:
    ark_check:
      enabled: true
    ark_board:
      enabled: false
      cron: "0 0 3 * * *"   # 可选定制覆盖该场景下的 Cron 表达式
  ```

---

## 八、 构建与全量索引规范 (`build.py` / `build-all.py`)

1. **单个应用的 `build.py`**：
   - 负责从上游获取最新状态、格式化输出该应用独立的 `app.yaml`。
   - 生成的 YAML 文件需使用 UTF-8 编码，保留标准多行缩进与合法 YAML 语法。
2. **全局聚合索引 `build-all.py`**：
   - 自动扫描 `apps/` 目录下所有 `app.yaml`。
   - 不进行破坏性重写，原汁原味聚合至仓库根目录的 `apps.json` 中供面板拉取消费。
3. **构建执行规则（重要）**：
   - **严禁在本地手动执行 `build.py`**；
   - 所有的构建、生成与全量索引统一交由 GitHub Actions (CI/CD) 在远端流水线中自动化触发与完成。
4. 每次新增yml的定义规范和概念的时候，需要更新readme和这个rule的规则。


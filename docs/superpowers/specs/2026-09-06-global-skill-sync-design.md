# 设计：一份 Skill，多宿主一致安装

## 目标

将仓库中的 `skill/` 定义为 `toxic-corporate-truth-teller` 的唯一维护源，并为 Codex、Cursor、WorkBuddy、WorkBuddy AI 以及其他兼容 Agent Skills 目录的工具提供同一套可重复安装与更新流程。同步后各宿主获得相同的指令、脚本、参考资料和资产；账号凭据、运行回执与本地内容不进入 Skill，也不随同步复制。

## 方案

新增一个 Python 标准库同步器。默认从当前仓库的 `skill/` 读取源文件，并自动识别当前用户目录下已存在的已知宿主 Skill 根目录：

| 宿主 | 默认安装根目录 |
| --- | --- |
| Codex | `~/.codex/skills` |
| Cursor | `~/.cursor/skills` |
| Gemini | `~/.gemini/skills` |
| WorkBuddy | `~/.workbuddy/skills` |
| WorkBuddy AI | `~/.workbuddy-ai/skills` |

同步器只自动写入已经存在的宿主根目录；未安装或无法确认的工具不会被凭空配置。用户可重复传入 `--target` 安装到其他兼容目录。每个目标均使用固定子目录 `toxic-corporate-truth-teller`。

## 数据流与安全

1. 校验源目录含有效 `SKILL.md`，并收集受管文件清单与 SHA256。
2. 对目标执行预检。首次安装直接写入；更新前将旧目标完整备份到用户目录下的 `.truth-teller-skill-backups/<宿主>/<时间戳>/`。
3. 将源 Skill 写入同级临时目录，复核文件清单和 SHA256，再原子替换目标。
4. 输出逐宿主结果与清单摘要；任一目标失败不删除其他宿主已经验证的安装。

忽略缓存、测试运行产物、`.git`、本地配置、凭据和交付回执。同步器不读取 `WECHAT_APP_SECRET` 等密钥，也不调用微信 API。备份目录不作为 Skill 自动发现目录，避免宿主同时加载新旧版本。

## 命令接口

- `python tools/sync_skill.py --check`：只比较，不修改。
- `python tools/sync_skill.py --all`：同步到已存在的已知宿主根目录。
- `python tools/sync_skill.py --target <目录>`：同步到一个额外的兼容 Skill 根目录，可重复使用。
- `python tools/sync_skill.py --all --dry-run`：显示将执行的操作。

默认没有 `--all` 或 `--target` 时只显示帮助并退出，不隐式修改用户目录。目标路径解析后必须位于明确指定的 Skill 根目录下，不能把用户主目录或磁盘根目录当作安装目标。

## README 契约

README 将明确区分：

- GitHub 仓库 `skill/` 是唯一维护源；本机安装目录是部署产物，不应单独编辑。
- Codex、Cursor、WorkBuddy、WorkBuddy AI 的本机路径与一条同步命令。
- Gemini 或其他工具仅在其 Skill 根目录已存在或用户显式传入时安装。
- 更新步骤为拉取仓库、运行测试、执行同步、运行 `--check`；不能靠手工复制部分文件判断已更新。
- 环境变量和账号配置由各宿主进程提供，绝不放入 Git 或 Skill 目录。

## 验证

新增离线测试覆盖首次安装、更新备份、多个目标、检查模式、排除运行产物和拒绝危险目标。完成后运行仓库全部测试、Skill 校验、Python 编译、差异检查，并对实际已存在的 Codex、Cursor、WorkBuddy、WorkBuddy AI 目标执行同步和哈希一致性核验。

## 范围边界

本次不修改各工具自身的安全策略、浏览器权限或微信发布授权；“使用同一套 Skill”只保证安装内容一致，不保证不同宿主开放相同工具能力。不会自动发表公众号文章，也不会删除用户现有草稿。

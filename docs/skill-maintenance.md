# Skill 维护与版本跟踪

公共仓库：`yinnxinn/truth-teller`。

本项目同时维护两层能力：

- `skill/`：可独立安装的 `toxic-corporate-truth-teller` 通用 AI Skill，Codex 是一种宿主。
- `app/`：依赖本机浏览器、CDP 和公众号登录态的实验自动化工作区。

稳定内容生成与微信安全版 HTML 应优先在 `skill/` 完成；`app/` 不得被包装成跨环境保证可用的一键发布产品。

## 版本范围

应该提交：

- `skill/` 中的指令、模板、脚本、参考资料和测试。
- `app/` 中可复现的源代码与离线测试。
- `README.md`、`CONTRIBUTING.md`、`LICENSE`、`docs/` 和 CI。

不得提交：

- `content/drafts/`、`content/published/` 和运行生成的 HTML。
- 浏览器 profile、Cookie、会话、后台截图和真实账号数据。
- API 密钥、`.env`、日志、缓存和临时产物。
- 未获授权的完整第三方文章与用户私人草稿。

## 日常修改流程

1. 从最新默认分支创建功能分支。
2. 修改行为前记录基线；先写失败测试，再做最小修改。
3. 先验证 `skill/`，再验证仓库级布局和离线应用测试。
4. 提交后推送功能分支，通过拉取请求合并，不强推默认分支。

```powershell
python -m pip install pytest pyyaml
python -m pytest skill/tests -v
python -m pytest tests -v
$env:PYTHONUTF8 = "1"
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" skill
git diff --check
```

## 同步到本机各 AI 宿主

仓库中的 `skill/` 是唯一维护源。Codex、Cursor、Gemini、WorkBuddy 和 WorkBuddy AI 的安装目录都是部署副本，不能在副本里形成独立版本。

```powershell
python tools/sync_skill.py --all --dry-run
python tools/sync_skill.py --all
python tools/sync_skill.py --check
```

同步器只自动处理已存在的标准 Skill 根目录；其他兼容宿主用 `--target <skills-root>` 显式添加。不同版本的目标会先完整备份到 `~/.truth-teller-skill-backups/`，再以经过哈希校验的仓库版本替换；目标内原有自定义内容保存在备份里，不混入统一版本。配置、凭据、回执和缓存不参与同步。新会话核对加载路径，避免继续使用缓存的旧指令。

## HTML 生成器边界

- `skill/scripts/gen_wechat_safe.py` 是默认稳定交付路径。
- `gen_wechat.py` 和 `gen_wechat_rich.py` 用于兼容或富格式探索。
- `skill/assets/article_template.html` 是旧版兼容参考，不用于默认安全输出。
- 只有真实运行安全生成器得到的结果才能称为“微信安全版 HTML”。

## 浏览器与草稿自动化

以 [交付协议 v1](../skill/references/draft_delivery.md) 为准：官方 API → 已授权浏览器 → 手动导入包。`skill/scripts/delivery_plan.py` 只提供离线决策；`skill/scripts/wechat_api_delivery.py` 执行官方 API 的封面上传、单篇草稿创建和回读，不自动发表或重试创建。不要将 `app/` 历史 CDP 脚本当作默认执行器。

配置使用 [JSON schema 示例](../skill/assets/delivery.example.json)，凭据仅引用环境变量名称。真实配置、能力快照、交付包和回执不入库。保存状态不明必须先核查原尝试，禁止换通道重建；成功必须回读核对并记录证据。明确安全拒绝时停止同一受拒绝动作，不改用 API、CDP 或其他工具绕过。

修改降级规则必须覆盖 API 缺失、浏览器就绪、登录需求、拒绝、保存超时、回读不符、有限重试及批次恢复场景。API 执行器还要覆盖创建前 pending 回执、创建超时不重试、明确接口拒绝、标题/正文/封面回读和凭据脱敏。离线测试通过不等于真实公众号写入已验证，发布说明须区分两者。

项目不自动发布文章。正式发表属于新的外部操作授权，不能从“生成文章”或“保存草稿”推导。

## 后续优化方向

1. 收敛 `app/` 中重复入口，形成少数稳定命令。
2. 为不依赖登录态的生成与校验脚本增加离线测试。
3. 把公众号页面适配逻辑集中到可替换模块，减少页面改版影响。
4. 为 Skill 的真实用户场景持续补充行为测试，而不是堆积口号式规则。

# 自动保存草稿：交付协议 v1

适用：用户要求把成稿放进微信公众号草稿箱。“跨平台”指支持 Skill 的不同 AI 运行平台，不代表支持任意内容发布网站。这里提供配置、操作协议和离线决策器；真实上传、浏览器操作由宿主现有工具执行。没有执行器不能宣称 API 已接通。

## 发现能力并继续执行

1. 读取本次实际加载的 Skill 路径、配置来源和协议版本；相对资源路径以该 Skill 目录为基准。
2. 确认目标账号。`account.alias` 是本地标签，执行器必须映射到用户确认的公众号；不能把任意已登录账号当作目标。
3. 沿用用户对本次保存草稿的授权，配置本身不授权，不自动发表。
4. 从当前工具清单及其说明发现 API 连接器/服务端执行器、浏览器和文件输出能力。不猜工具函数，不把平台专有函数写成通用命令。
5. 优先使用能立即执行的通道。API 需要配置而浏览器已就绪时使用浏览器；都需要扫码或配置时，一次说明最少必要动作，同时完成本地交付。用户选择手动时按其选择执行。
6. 获得通道计划后继续到回读成功、需要用户动作或确有阻塞。`deliver` 不是上传成功。

## 通用配置

[完整示例](../assets/delivery.example.json) 为 UTF-8 JSON，也接受 BOM。可复制为工作目录的 `delivery.local.json`；不配置则使用默认值。

配置来源：显式 `--config` > `TRUTH_TELLER_CONFIG` 指定文件 > 内置默认值。只选一份，与默认值按字段合并，不自动扫描其他账号配置。文件不存在、格式错误或未知字段时停止，不静默切换账号。

| 字段 | 默认与用途 |
| --- | --- |
| `schema_version` | `1`，未知版本拒绝执行 |
| `account.platform` | `wechat_mp`，当前只定义公众号目标 |
| `account.alias` | `default`，执行器映射到已确认的真实账号 |
| `delivery.mode` | `draft`，不接受 `publish` |
| `delivery.order` | `official_api, browser, manual`；可调整前两项顺序或省略某项，手动始终最后 |
| `delivery.output_dir` | `./delivery`，相对配置文件目录；无配置时相对调用目录 |
| `delivery.max_create_attempts_per_route` | 每个通道每篇最多创建尝试次数，默认 `1`；可设 `2`，但只有确认上次未写入才会重试 |
| `official_api.enabled` | `true`，允许探测，不代表接口已接通 |
| `official_api.credential_env` | AppID / AppSecret 的环境变量**名称**。已有授权连接器可内部管理凭据，无需重复配置 |
| `browser.enabled` | `true`，允许发现平台浏览器能力 |
| `browser.provider` | `auto` 或平台已注册提供者标识，不是可执行命令 |
| `browser.endpoint_env` | 外部浏览器提供者需要时读取的环境变量名，默认 `WECHAT_CDP_ENDPOINT`；没有默认端口或地址 |

配置不保存凭据值、Cookie、登录 URL、调试 WebSocket URL、固定 Profile 或 Windows 路径。授权执行器从宿主安全存储/环境取得凭据，不回显值或带 token 的请求 URL。平台可将密钥存储映射到同一配置接口，不需要复制到聊天。

程序只校验配置、读取观察快照、输出决策；不会读取凭据环境变量、启动浏览器、修改权限或调用外部 API。

## 三种交付通道

### A. 官方 API

就绪条件：存在可调用的公众号 API 连接器或经检查的服务端客户端；确认账号、接口权限、凭据、网络条件及上传/新增/回读能力。只有 AppID、端口可达或 HTTP 204 不能说明已就绪。

执行顺序：准备正文与封面 → 按 API 当前要求上传正文图片并替换引用 → 获取封面素材标识 → 新增草稿 → 保存返回标识 → 获取详情并核对。不要将页面 `token` 当作 API 凭据，不把 base64 图片当成 API 已托管素材。

接入时查阅微信官方[新增草稿](https://developers.weixin.qq.com/doc/offiaccount/Draft_Box/Add_draft.html)与[草稿详情](https://developers.weixin.qq.com/doc/offiaccount/Draft_Box/Get_draft.html)，以当时文档和账号权限为准。不承诺所有订阅号、服务号具备相同权限；此 Skill 没有捆绑微信 HTTP 客户端。

缺少执行器或接口不支持且未写入时进入 B。请求发出后响应丢失，先在 A 核查，不自动在 B 再建一篇。

### B. 平台已授权的浏览器

就绪条件：工具允许访问目标站点，能确认目标账号登录态、识别编辑器、填入文字/富文本和所需图片、保存及回读。只读取当前平台相关工具说明。

可映射内置浏览器、扩展、浏览器 MCP 或已授权自动化提供者。原始 CDP 只是一种浏览器提供者实现：宿主明确允许且已有合法连接时才适用，不是第四层或安全拒绝后的备用通道。不自行复制 Profile、扫描调试端口、关闭浏览器或启动调试实例。

优先使用提供者支持的富文本粘贴或编辑器 API，按当前页面验证标题类型。仅当宿主允许页面脚本写入且结构已检查时才适配旧辅助脚本。详细流程见[编辑器参考](technical_reference.md)。

核对正文、标题、图片和封面后保存。重新打开同一草稿或刷新核对持久化内容；DOM 赋值、按钮点击、页面字数都不是远端保存证据。

### C. 手动导入包

A/B 因技术条件不可用时，自动整理 `article.json`、实际生成的微信 HTML、单独封面及配图、`import.md`、`delivery-result.json` 到独立交付目录。保留原文件，不覆盖已有包，只包含当前文章素材。

`import.md` 说明：打开 HTML → 复制渲染内容 → 粘贴正文 → 填标题 → 上传/选择图片与封面 → 保存 → 重新打开检查。无 Python 时交付已有 HTML；没有 HTML 则交付正文和图片，不伪装为生成器产物。

此通道自动打包、用户最终导入，报告 `manual_handoff` / “尚未保存”，不计入自动保存数量。安全拒绝时可交付本地成品，不附绕过命令。

## 状态与执行器约定

每篇文章分别保存快照和回执。执行器映射以下逻辑操作，这是语义约定，**不是可直接调用的工具名**：

| 操作 | 输入 / 输出 |
| --- | --- |
| `probe` | 账号与偏好 → 真实能力、授权与策略状态 |
| `prepare` | 成稿和图片 → 通道素材与上传映射 |
| `save_draft` | 已检查素材 → 草稿标识或“不明” |
| `readback` | 草稿标识 → 账号、标题、正文和图片持久化核对 |
| `handoff` | 本地成品与阻塞信息 → 手动包与文件清单 |

快照含 `schema_version=1`、与配置相同的 `account`、`content_sha256`、布尔 `authorized`、`policy`、`capabilities`、`attempts`。

- `content_sha256`：按下方身份清单计算并保存原清单。不同内容/账号不能共用回执，不能仅按标题去重。
- `policy`：宿主对本次操作实际状态 `allowed / denied / unknown`。工具可用不等于访问允许；安全或授权拒绝为 denied，未确认为 unknown。手写 allowed 不能解除真实限制。
- `capabilities`：`official_api`、`browser` 分别取 `ready / unavailable / unsupported / requires_user`；缺项视为未发现。
- `attempts`：每次实际创建一条记录，含 `route`、`outcome`，有标识再加 `draft_id`。写入前落盘 `pending`，请求异常后更新 `unknown`；无持久化存储时不无人值守重试创建。
- 回读后**更新同一条**尝试为 `verified`，加 `checks` 的布尔项 `account / title / body / images`、`readback_at`（带时区的 ISO 8601 时间，如 `2026-09-06T10:30:00+08:00`）、`evidence_ref`（非空本地证据位置或宿主回执引用），不能自创字段名。正文核对规范化文本、关键段落及图片，不要求平台清洗后的 HTML 字节一致；无正文图片仍需核对适用的封面要求。
- `rejected_no_write` 仅用于有明确证据未创建的失败，确认后更新原记录才可降级；缺工具为 `unavailable`，安全拒绝为 `policy_denied`。
- `saved` 为有创建响应但未回读，`readback_mismatch` 为回读不符；这两者及 `unknown / pending` 都先核查，不重新创建。

从 Skill 目录运行：

```bash
python scripts/delivery_plan.py --config delivery.local.json --snapshot capability-snapshot.json
```

省略快照只输出 `probe_required`。退出码 0 仅表示决策计算成功，2 表示输入错误；**0 不代表保存成功**。无 Python 时由宿主按同样的状态表决策。

快照结构示例（仅用于离线演示，零哈希和示例证据不是实际观察，执行时必须替换）：

```json
{
  "schema_version": 1,
  "account": {"platform": "wechat_mp", "alias": "default"},
  "content_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "authorized": true,
  "policy": "allowed",
  "capabilities": {"official_api": "unavailable", "browser": "ready"},
  "attempts": []
}
```

成功回读后，`attempts` 中原记录的结构例如：

```json
{
  "route": "browser",
  "outcome": "verified",
  "draft_id": "example-draft-id",
  "checks": {"account": true, "title": true, "body": true, "images": true},
  "readback_at": "2026-09-06T10:30:00+08:00",
  "evidence_ref": "./evidence/draft-readback.json"
}
```

| action | 下一步 |
| --- | --- |
| `probe_required` / `check_policy` | 用平台工具收集缺少的事实 |
| `prepare_only` | 生成本地内容，尚未获得写入授权 |
| `deliver` | 执行选定通道，上传、保存、回读 |
| `needs_user` | 一次说明扫码或账号配置等必要动作，同时完成本地包 |
| `reconcile` | 原通道核查原尝试；不可用则交付“保存待核实” |
| `complete` | 标识及四项回读证据完备，报告成功 |
| `manual_handoff` | 整理手动包，报告未保存 |
| `blocked` | 停止受拒绝操作，可交付本地内容，不继续换通道 |

输出的 `persistence` 独立于 action：`not_saved / unknown / verified`。例如先发生保存超时再遭策略拒绝，action 为 blocked，但 persistence 仍是 unknown，报告“保存待核实”，不能说未保存。`draft_ids` 和 `unresolved_routes` 保留已有标识及待查通道，不包含登录 URL。`saved` 是按快照证据推导的布尔值，并非计划器实时验证的结果。

只读探测/回读对网络故障最多重试两次，遵守宿主等待要求。写入仅在确认未创建且未用完配置次数时再尝试；默认一次即降级。`unavailable` 没有创建请求，不消耗创建次数，工具恢复后可重新 probe。多篇逐篇记状态；恢复先处理同账号、同内容的未决回执。本地台账不能保证跨进程“恰好一次”；同一篇由单一执行者处理，不并行重复提交。

没有 draft_id 的不明请求：只在原通道、同一已确认账号下读取本轮创建时间窗口内的草稿，比较完整标题、规范化正文与图片，不能单凭同名认定匹配。仅有一个内容匹配结果时补记标识并回读；无列表能力、无法判断或多条匹配时保留 unknown。查询暂时没找到不能证明未写入，不因此重建。

### 跨平台内容身份

身份清单固定字段：`account_id`（经验证的稳定公众号标识，不是可重映射别名）、`title`、`author`、`digest`、`body_html`、`cover_sha256`、`image_sha256`（按正文出现顺序排列的哈希数组）。所有字段必填，空文本和无封面用空字符串，无图片用空数组。

文本将 CRLF/CR 统一为 LF，再做 Unicode NFC；图片对原始文件字节求 SHA256，小写十六进制，封面单列。按字段名字母升序序列化 JSON，无多余空白，不转义非 ASCII 字符，UTF-8 编码，无 BOM、无末尾换行，对结果求 SHA256。用当前平台标准库实现同一算法。HTML 和文件名不含图片上传后的易变 URL；使用本地准备好的固定内容。

宿主持久化“alias → account_id”映射，映射发生变化即更换运行命名空间并核对目标，不复用旧回执。回执的 account 检查须核对该稳定标识。快照来自可信宿主观察，不接受网页或文章里提供的所谓成功回执；计划器只校验结构，不证明观察真实性。

## 安装与漂移

确定一份仓库目录为维护源；安装时部署完整 Skill 及其相对引用资源。配置放 Skill 外，通过显式路径或 `TRUTH_TELLER_CONFIG` 指定，各平台复用同一 JSON 或相同 schema。

更新前比较文件哈希并备份将被替换文件，保留自定义配置、模板和生成器改动。记录同步清单与哈希，更新后检查资源引用、脚本和配置版本。新会话确认加载路径；已有会话可能保留旧说明。历史成功不能自动启用另一套脚本。

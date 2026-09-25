<p align="center">
  <img src="./src/icon.png" alt="ChatGPT Tag Highlighter 图标" width="96">
</p>

<h1 align="center">ChatGPT Tag Highlighter</h1>

<p align="center">
  用 <b>[TODO]</b>、<b>[BUG]</b> 这样的标题标签给 ChatGPT 侧边栏上色、<br>
  按标签筛选，并让超长对话保持流畅。
</p>

<p align="center">
  <a href="https://chromewebstore.google.com/detail/chatgpt-tag-highlighter/lplghggkggkbkkakjabafjenjlekogbm"><b>Chrome 应用商店</b></a> ·
  <a href="https://addons.mozilla.org/firefox/addon/chatgpt-tag-highlighter/"><b>Firefox 附加组件</b></a> ·
  <a href="./ReadMe.md">English</a>
</p>

<p align="center">
  <a href="https://github.com/D0n9X1n/chatgpt-tag-highlighter/actions/workflows/test.yml"><img alt="Tests" src="https://github.com/D0n9X1n/chatgpt-tag-highlighter/actions/workflows/test.yml/badge.svg?branch=main"></a>
  <a href="https://github.com/D0n9X1n/chatgpt-tag-highlighter/actions/workflows/codeql.yml"><img alt="CodeQL" src="https://github.com/D0n9X1n/chatgpt-tag-highlighter/actions/workflows/codeql.yml/badge.svg?branch=main"></a>
  <a href="https://github.com/D0n9X1n/chatgpt-tag-highlighter/releases"><img alt="GitHub release" src="https://img.shields.io/github/v/release/D0n9X1n/chatgpt-tag-highlighter?include_prereleases&logo=github&label=release&color=brightgreen"></a>
  <a href="https://chromewebstore.google.com/detail/chatgpt-tag-highlighter/lplghggkggkbkkakjabafjenjlekogbm"><img alt="Chrome Web Store" src="https://img.shields.io/chrome-web-store/v/lplghggkggkbkkakjabafjenjlekogbm?logo=googlechrome&logoColor=white&label=chrome&color=brightgreen"></a>
  <a href="https://chromewebstore.google.com/detail/chatgpt-tag-highlighter/lplghggkggkbkkakjabafjenjlekogbm"><img alt="Chrome Web Store users" src="https://img.shields.io/chrome-web-store/users/lplghggkggkbkkakjabafjenjlekogbm?logo=googlechrome&logoColor=white&label=users"></a>
  <a href="https://addons.mozilla.org/firefox/addon/chatgpt-tag-highlighter/"><img alt="Firefox Add-ons" src="https://img.shields.io/amo/v/chatgpt-tag-highlighter?logo=firefoxbrowser&logoColor=white&label=firefox&color=brightgreen"></a>
  <a href="https://addons.mozilla.org/firefox/addon/chatgpt-tag-highlighter/"><img alt="Firefox users" src="https://img.shields.io/amo/users/chatgpt-tag-highlighter?logo=firefoxbrowser&logoColor=white&label=users"></a>
  <a href="./LICENSE"><img alt="License: MIT" src="https://img.shields.io/github/license/D0n9X1n/chatgpt-tag-highlighter?color=brightgreen"></a>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./img/hero-dark.png">
    <img src="./img/hero-light.png" alt="ChatGPT 侧边栏中带彩色标柱和筛选标签的会话，以及输入框上方显示当前会话标签的横幅" width="860">
  </picture>
</p>

---

## 它能做什么

- **给带标签的会话上色**：把会话命名为 `[TODO] 修复构建流水线`，它在侧边栏里就会有彩色标柱和背景；当前打开的会话高亮更明显。
- **按标签筛选**：会话列表上方的标签按钮可以只显示你选中的标签，支持多选，刷新后选择仍然保留。
- **告诉你身在何处**：输入框上方的横幅显示当前会话的标签和标题，点击即可跳到最新消息。
- **让长对话保持流畅**：屏幕外的消息会跳过渲染，但不会被删除，滚动和页面查找照常可用。[性能数据见下文](#长对话依然流畅)。
- **清理无标签会话（可选）**：开启后，筛选栏会多一个按钮，列出所有不匹配任何规则的会话，输入 `delete` 确认后才删除。置顶、加星和已归档的会话会保留。[详见下文](#删除无标签会话)。
- **不打扰你**：规则实时生效，自动跟随 ChatGPT 的深色/浅色主题，除了存储和两个 ChatGPT 站点外不申请任何权限。

## 快速开始

1. 从 [Chrome 应用商店](https://chromewebstore.google.com/detail/chatgpt-tag-highlighter/lplghggkggkbkkakjabafjenjlekogbm) 或 [Firefox 附加组件](https://addons.mozilla.org/firefox/addon/chatgpt-tag-highlighter/) 安装。
2. 在 ChatGPT 里把几个会话改名，以标签开头，例如 `[TODO] …` 或 `[BUG] …`。
3. 完成。扩展已自带四条规则：**[TODO]**、**[BUG]**、**code**、**help**。想修改就打开扩展的 **Options（设置）** 页。

## 设置

<p align="center">
  <img src="./img/settings.png" alt="设置页：通用选项、标签规则表格和规则测试器" width="760">
</p>

**标签规则**从上到下依次匹配，第一个命中的规则生效，拖动 ≡ 可调整顺序。每条规则包含：

| 字段 | 含义 |
|---|---|
| Tag | 要查找的文字，区分大小写。 |
| Match | `startsWith`：标题以该标签开头（最适合 `[TAG]` 前缀）；`includes`：标题任意位置包含该标签。 |
| Color | 选择预置颜色，或输入任意 `#RRGGBB`。 |
| Hide | 在侧边栏中隐藏命中的会话，按 `Alt+H` 可临时显示。 |
| Overlay | 打开命中的会话时显示标签横幅。 |

**规则测试器**会告诉你某个标题会命中哪条规则。**Export** 把设置以 JSON 复制出来，**Import** 再导入回去。所有修改都会自动保存。

**通用选项：**

| 选项 | 默认 | 作用 |
|---|---|---|
| Speed up long chats（加速长对话） | 开 | 在 20 条及以上消息的对话中，浏览器跳过渲染屏幕外的消息；最新的 4 条始终正常渲染。 |
| Max chat turns to keep（保留的最大轮次） | 0（关闭） | 从页面上移除较早的消息（不会从你的账号中删除），刷新或重新打开会话后恢复。 |
| Hide right navigation bar（隐藏右侧导航栏） | 开 | 在旧版 ChatGPT 布局中隐藏消息缩略导航；当前布局没有这个导航栏，因此不起作用。 |
| Dim untagged conversations（弱化无标签会话） | 关 | 淡化不匹配任何规则的会话。 |
| Show badge counter（显示角标计数） | 开 | 在扩展图标上显示当前可见的已标记会话数量。 |
| Show “Delete untagged chats” button（显示“删除无标签会话”按钮） | 关 | 在筛选栏添加 **Delete untagged…** 按钮。见[删除无标签会话](#删除无标签会话)。 |

**键盘快捷键：** `Alt+H`（macOS 上为 `Option+H`）显示/隐藏被规则隐藏的会话；`Alt+F` 聚焦筛选栏。

### 删除无标签会话

默认关闭。开启 **Show “Delete untagged chats” button** 后，点击筛选栏中的 **Delete untagged…**：

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./img/delete-untagged-dark.png">
    <img src="./img/delete-untagged-light.png" alt="删除无标签会话对话框：列出不匹配任何规则的会话，确认框中已输入 delete" width="760">
  </picture>
</p>

1. 扩展向 ChatGPT 获取完整的会话列表（不只是侧边栏已加载的部分），列出所有标题不匹配任何规则的会话。此时还不会删除任何内容。
2. 置顶、加星和已归档的会话会保留，所有命中规则的会话（包括被规则隐藏的）也会保留。
3. 输入 `delete` 并确认。删除前会再检查一次列表，预览之后被你加标签、置顶、加星、归档或删除的会话会被跳过。随后会话会逐个删除，使用的请求与 ChatGPT 自带的 **Delete** 相同。**Stop** 会在当前会话删除完后停止，遇到第一个错误也会停止。

ChatGPT 侧边栏无法恢复已删除的会话，请在确认前检查列表。此功能依赖 ChatGPT 未公开的网页接口，这些接口可能随时变化。

## 长对话依然流畅

超长对话会变慢，是因为浏览器要为每一条消息计算样式和布局，即使它们远在屏幕之外。开启 **Speed up long chats** 后，较早的消息会使用 `content-visibility: auto`，浏览器在它们接近屏幕前会跳过这些工作。每条消息保留实测高度作为占位，所以滚动条不会跳动。

在 Chrome 中对真实 ChatGPT 页面、约 200 条消息的对话分别关闭和开启该选项的测量结果：

| 工作 | 关闭 | 开启 |
|---|---:|---:|
| 4 次调整窗口大小的样式重算 | 2,059 ms | 449 ms |
| 同样调整下的布局 | 59 ms | 20 ms |
| 10 次全页面样式变化（例如切换主题） | 1,255 ms | 296 ms |
| 滚动整个对话时最慢的一帧 | 120 ms | 27 ms |

以上数据来自一台机器，实际结果会有差异。少于 20 条消息的对话不受影响。扩展自身的开销很小：同一次测试中，显示横幅每帧增加不到 0.1 ms。

## 权限与隐私

- **`storage`**：保存你的规则。使用浏览器扩展的同步存储，因此浏览器可能会在你已登录的设备之间同步这些设置。
- **站点访问**：仅限 `https://chatgpt.com/*` 和 `https://chat.openai.com/*`，用于给这些页面加样式；无法访问其他任何网站。
- 扩展会读取**侧边栏会话标题**来匹配规则，读取**消息高度**来加速长对话；不会读取或保存消息正文。
- 如果使用**删除无标签会话**，扩展会通过你已登录的 ChatGPT 会话列出会话并删除你确认的那些。这些请求只发往 ChatGPT。会话令牌只在本次操作期间保存在内存中，从不存储。
- 没有统计分析、没有追踪、没有自己的服务器。详见[隐私政策](./Privacy%20Policy.md)。

## 常见问题

- **没有任何高亮？** 确认标题里确实包含该标签。匹配区分大小写，`startsWith` 要求标签位于标题最开头。可以用设置页里的规则测试器检查。修改规则后无需刷新页面。
- **设置页空白？** 请从扩展的 Options 入口打开，不要用 `file://` 路径打开，否则无法使用存储 API。
- **ChatGPT 改版后功能失效？** 欢迎[提交 issue](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues)，并附上浏览器版本。

## 开发

扩展是纯 JavaScript，没有依赖，也没有打包工具。`src/` 里是源码和两个 manifest 模板，但没有 `manifest.json`，所以加载前需要先构建：

```sh
./publish.sh --version 0.0.99            # 生成 dist/chrome/、dist/firefox/、.zip 和 .xpi
```

- **Chrome：** 打开 `chrome://extensions`，开启开发者模式，点击 **Load unpacked**，选择 `dist/chrome/`。
- **Firefox：** 打开 `about:debugging#/runtime/this-firefox`，点击 **Load Temporary Add-on**，选择 `dist/firefox/manifest.json`。

每次修改后重新构建、重新加载扩展，然后刷新 ChatGPT 标签页。

<details>
<summary><b>测试、架构与实机测试规则</b></summary>

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r tests/requirements.txt && playwright install chromium

./publish.sh --version 0.0.99                     # 测试针对 dist/chrome 运行
CI=true pytest tests/test_extension.py -v         # 完整测试，使用一次性浏览器配置
CI=true pytest tests/test_extension.py -k TestContentScript -v
for f in src/*.js; do node --check "$f"; done     # 语法检查
npx --yes web-ext@8.3.0 lint --source-dir dist/firefox --warnings-as-errors=false --self-hosted
```

- `TestContentScript` 在 `https://chatgpt.com/` 下的仿真 ChatGPT 页面上运行**打包后的**内容脚本；其他测试覆盖设置页、配置迁移和导入/导出。
- `background.js` 初始化并迁移配置，`options.js` 编辑配置，`content.js` 应用配置并通过 `storage.onChanged` 实时更新。三者共享存储键 `tagHighlighterConfigV1`；筛选选择单独保存在本地存储的 `tagHighlighterUiStateV1` 中。
- 新增配置字段必须在三个脚本中都有安全的默认值。
- **在 chatgpt.com 上实机测试：** 不要改动 `tests/.test-profile/`，里面有登录状态。整个测试过程只用一个浏览器会话，因为 ChatGPT 的 Cookie 有效期很短。绝不发送、新建、重命名或删除会话。

更多内容见 [CONTRIBUTING](./.github/CONTRIBUTING.md) 和 [CLAUDE.md](./CLAUDE.md)（其中列出了扩展依赖的 ChatGPT 页面元素）。
</details>

## License

[MIT](./LICENSE)

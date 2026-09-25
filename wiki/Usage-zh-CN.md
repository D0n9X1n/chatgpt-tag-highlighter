# 使用

[English](Usage)

## 安装

- **Chrome、Edge、Brave、Arc：** 从 [Chrome 应用商店](https://chromewebstore.google.com/detail/chatgpt-tag-highlighter/lplghggkggkbkkakjabafjenjlekogbm) 安装。
- **Firefox：** 从 [Firefox 附加组件](https://addons.mozilla.org/firefox/addon/chatgpt-tag-highlighter/) 安装。
- **本地构建：** 运行 `./publish.sh --version 0.0.99`，然后在 `chrome://extensions` 用 **Load unpacked** 加载 `dist/chrome/`，或在 `about:debugging` 用 **Load Temporary Add-on** 加载 `dist/firefox/manifest.json`。`src/` 中没有 `manifest.json`，不能直接加载。参见 [开发与发布](Development-and-Release-zh-CN)。

## 给会话加标签

在 ChatGPT 中把会话改名，让标题以标签开头，例如 `[TODO] 修复构建流水线` 或 `[BUG] 登录令牌提前过期`。安装时已自带四条规则：**[TODO]**（黄）、**[BUG]**（红）、**code**（蓝）、**help**（绿）。可在 [设置](Configuration-zh-CN) 中修改。

带标签的会话会有彩色左侧标柱和背景；当前打开的会话背景更明显、标柱更粗。匹配区分大小写，`startsWith` 规则要求标签位于标题最开头。

## 筛选侧边栏

当至少有两条规则没有设为 Hide 时，会话列表上方会出现标签按钮。点击一个或多个标签按钮，只显示这些标签的会话（命中任意一个选中标签即显示）。**All** 会清除选择。选择在刷新后保留，并在多个 ChatGPT 标签页之间共享。

## 标签横幅

当打开的会话命中一条开启了 **Overlay** 的规则时，输入框上方的横幅会显示它的标签颜色和标题。点击横幅会跳到最新消息，输入框保持焦点。横幅显示期间，ChatGPT 自带的"滚动到底部"按钮会被隐藏，避免出现两个；在无标签会话中不会动 ChatGPT 的按钮。

## 角标

扩展图标上显示已加载的侧边栏会话中、带标签且未被规则隐藏的数量。可在 [设置](Configuration-zh-CN) 中关闭。

## 键盘快捷键

| 按键 | 作用 |
|---|---|
| `Alt+H`（macOS 上为 `Option+H`） | 显示/隐藏被 Hide 规则隐藏的会话 |
| `Alt+F` | 聚焦筛选栏 |
| `Enter` 或 `Space` | 切换当前聚焦的标签按钮 |

# ChatGPT Tag Highlighter

一个轻量级浏览器扩展：根据聊天标题里的标签（例如 **[TODO]**、**[BUG]**）自动高亮 ChatGPT 侧边栏会话。
效果是：**左侧彩色标柱 + 柔和背景**，让你一眼找到重要对话、快速跳转、不再“翻聊天翻到心态爆炸”。

![LOGO](./src/icon.png)

---

## 为什么需要它

当你把 ChatGPT 当作第二大脑用久了，侧边栏会迅速变成“信息迷雾”：

- 这条是 bug 现场？还是当时的灵感？
- 那条是待办？还是已经做完的？
- 点进去一看不对又退出来……重复十次，最后直接新开一个 chat（然后更乱）

**ChatGPT Tag Highlighter** 只做一件事：
> 让你的侧边栏像“任务列表”一样可视化，有秩序、有优先级。

---

## 功能特性

-  **标签高亮**：根据标题标签高亮侧边栏会话（例如 `[TODO]`、`[BUG]`）
-  **设置页可配置**：
  - 增加/删除标签
  - 匹配方式：`startsWith`（推荐、最快）或 `includes`
  - 颜色：预置配色（Gruvbox 风格）或自定义 `#RRGGBB`
-  **选中态 vs 非选中态区分**：
  - 选中的会话更明显（更强背景 + 更粗标柱）
-  **性能优先**：
  - 只处理侧边栏会话列表
  - 增量更新（新出现/变更的才处理）
  - 批量刷新，减少 DOM 操作

---

## 截图

### 侧边栏预览
![Sidebar Preview](./img/1.png)

### 设置页面
![Settings](./img/2.png)

---

## 安装方式

### Chrome（开发者模式）
1. 打开 `chrome://extensions`
2. 开启 **Developer mode**
3. 点击 **Load unpacked**
4. 选择项目目录（包含 `src/` 的那个文件夹）

### Firefox（临时加载，开发调试用）
1. 打开 `about:debugging#/runtime/this-firefox`
2. 点击 **Load Temporary Add-on**
3. 选择扩展输出目录（或打包后的 `xpi`）

---

## 使用方法

### 1）给聊天标题加标签
把对话标题写成这种格式即可：

- `[TODO] 修复发布脚本`
- `[BUG] Firefox 上传缺少字段`

### 2）在设置页配置规则
打开扩展的 **Options / Settings**，你可以配置：

- **Tag**：要匹配的标签（建议用 `[TAG]` 风格）
- **Match**：
  - `startsWith`：标题以标签开头才命中（最快、推荐）
  - `includes`：标题包含标签即可命中（更灵活）
- **Color**：
  - 选择预置颜色
  - 或输入自定义 `#RRGGBB`

---

## 默认规则

扩展首次安装会自动写入（seed）两条默认规则：

- **[TODO]** → Bright Yellow
- **[BUG]** → Bright Red

你可以在设置页随时修改或删除。

---

## 权限说明

- `storage`：用于在浏览器本地保存你的标签/颜色配置

站点访问（仅用于在这些页面应用样式）：
- `https://chatgpt.com/*`
- `https://chat.openai.com/*`

---

## 隐私说明

- 不收集任何数据
- 不上传任何信息到服务器
- 不做埋点/统计/分析
- 仅在本地读取“侧边栏会话标题”用于匹配高亮
- 配置仅保存在浏览器扩展存储中

---

## 常见问题

### 没有任何高亮效果？
- 确认聊天标题里确实有标签（例如 `[TODO] ...`）
- 打开设置页确认规则存在
- 修改设置后建议刷新一次 ChatGPT 页面

### 设置页崩溃/白屏？
- 不要用 `file://...` 直接打开 `options.html`
- 必须从扩展的 **Options / Preferences** 打开（这样才有 `storage` API）

---

## License

See [License](./LICENSE)


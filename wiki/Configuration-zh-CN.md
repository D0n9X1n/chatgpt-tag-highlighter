# 设置

[English](Configuration)

从浏览器的扩展菜单打开扩展的 **Options（设置）** 页。不要用 `file://` 路径打开 `options.html`，那样无法使用存储 API。所有修改都会自动保存。

![设置页](https://raw.githubusercontent.com/D0n9X1n/chatgpt-tag-highlighter/main/img/settings.png)

## 标签规则

规则从上到下依次匹配，**第一个命中的规则**决定颜色、隐藏、筛选和横幅。拖动 ≡ 可调整顺序。

| 字段 | 含义 |
|---|---|
| Tag | 要查找的文字，区分大小写。 |
| Match | `startsWith`：标题以标签开头（最适合 `[TAG]` 前缀）；`includes`：标题任意位置包含该标签。 |
| Color | 预置颜色或任意 `#RRGGBB`，始终以十六进制保存。 |
| Hide | 在侧边栏中隐藏命中的会话，`Alt+H` 可临时显示。 |
| Overlay | 打开命中的会话时显示标签横幅。 |

修改规则会实时应用到已打开的 ChatGPT 标签页。

## 通用选项

| 选项 | 默认 | 作用 |
|---|---|---|
| Speed up long chats（加速长对话） | 开 | 在 20 条及以上消息的对话中跳过渲染屏幕外的消息。见 [长对话](Long-Chats-zh-CN)。 |
| Max chat turns to keep（保留的最大轮次） | 0（关闭） | 从页面上移除较早的消息（不会从你的账号中删除），刷新或重新打开会话后恢复。 |
| Hide right navigation bar（隐藏右侧导航栏） | 开 | 在旧版 ChatGPT 布局中隐藏消息缩略导航；当前布局没有这个导航栏，因此不起作用。 |
| Dim untagged conversations（弱化无标签会话） | 关 | 淡化不匹配任何规则的会话。 |
| Show badge counter（显示角标计数） | 开 | 在扩展图标上显示可见的已标记会话数量。 |
| Show “Delete untagged chats” button（显示“删除无标签会话”按钮） | 关 | 在筛选栏添加 **Delete untagged…** 按钮。见 [使用](Usage-zh-CN)。 |

## 规则测试器

在 **Rule Tester** 中输入会话标题，即可看到会命中哪条规则、其他规则为什么没命中。

## 导入与导出

**Export** 把全部设置以 JSON 复制到剪贴板。**Import** 接受粘贴的 JSON；无效 JSON 或没有任何规则的设置会被拒绝。

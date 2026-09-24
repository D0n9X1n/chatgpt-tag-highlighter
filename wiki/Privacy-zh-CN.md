# 隐私

[English](Privacy)

## 读取什么

- **侧边栏会话标题**，用于匹配标签规则。
- **ChatGPT 的主题**（浅色或深色），用于让横幅外观一致。
- 页面上**消息的尺寸**，用于"加速长对话"。
- 如果设置了 **Max chat turns**，扩展会从页面上移除较早的消息元素。它从不读取消息正文、提示词、回复或文件。

## 保存什么

- **标签规则和选项**保存在浏览器扩展存储中，使用 `storage.sync`（以 `storage.local` 作为后备）。
- **选中了哪些筛选标签**，保存在 `storage.local`。
- 如果开启了浏览器同步，浏览器可能会通过它自己的同步服务把这些设置复制到你已登录的其他设备。扩展本身从不把它们发送到任何地方。

## 从不做什么

- 没有统计分析、追踪或遥测。
- 没有自己的服务器，也不与第三方共享。
- 完整内容见 [隐私政策](https://github.com/D0n9X1n/chatgpt-tag-highlighter/blob/main/Privacy%20Policy.md)。

## 权限

- `storage`：保存规则和选项。
- 仅访问 `https://chatgpt.com/*` 和 `https://chat.openai.com/*`，用于给这些页面加样式。

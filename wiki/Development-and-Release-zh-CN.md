# 开发与发布

[English](Development-and-Release)

## 构建

```sh
./publish.sh --version 0.0.99
```

这会生成 `dist/chrome/` 和 `dist/firefox/`（各自带有生成的 `manifest.json`），以及一个 `.zip` 和一个 `.xpi`。`dist/` 是生成目录，已被 gitignore；`src/` 是唯一的源码。加载 `dist/chrome/` 或 `dist/firefox/manifest.json`，每次修改后重新构建。`publish.sh --version` 只会把版本号写入构建出的 manifest。

## CI 检查

每个拉取请求和每次推送到 `main` 都必须通过：

- JavaScript 语法检查，以及 `scripts/release-check.py`：两个 manifest 版本号一致，且 `CHANGELOG.md` 中有对应小节。
- 构建 Chrome 和 Firefox 包。
- 在 Xvfb 下针对 Chrome 包运行 Playwright 测试。
- 对 Firefox 包运行 `web-ext lint`。
- Wiki 检查器和 Wiki 发布脚本的自测。
- `CI status`：一个汇总任务，上面任何一项失败，它就失败。请在分支保护中将它设为必需检查。

所有 action 都固定到提交 SHA 并附带版本注释，每个任务和步骤都设置了超时。

本地运行方式见 [测试](Testing-zh-CN)。

## 发布

1. 在 `src/manifest.chrome.json` 和 `src/manifest.firefox.json` **两个文件**中更新 `version`，并在 `CHANGELOG.md` 中添加对应的 `## [X.Y.Z]` 小节。
2. 合并到 `main`，等待 CI 通过。
3. 给该提交打上 `vX.Y.Z` 标签并推送。`vX.Y.Z-rc.1` 这样的标签会发布为预发布版本。

发布流程会检查标签与两个 manifest 一致、CHANGELOG 中有对应小节，并且被打标签的提交在 `main` 上且 CI 已成功。然后构建带 SHA-256 校验和的 `.zip` 和 `.xpi`，并发布 GitHub Release，发布说明取自 CHANGELOG 对应小节。上传到 Chrome 应用商店和 Firefox 附加组件仍需手动完成。Chrome 只接受纯数字版本号（最多四段，用点分隔），因此 manifest 保持 `X.Y.Z`，标签上的 `-后缀` 只用于把 GitHub Release 标记为预发布。

## Wiki 源文件与发布

- 仓库中受版本控制的 `wiki/` 目录是本 Wiki 的唯一来源。请在那里编辑页面，不要在 GitHub 上编辑。
- 每个页面都有英文文件和 `-zh-CN` 文件，内容事实一致、标题层级一致。链接使用不带 `.md` 的页面名，Home 链接到所有页面，流程图使用 Mermaid。
- `scripts/check-wiki.py` 在 CI 中强制执行这些规则。
- 每次推送到 `main`，Publish wiki 工作流会运行 `scripts/publish-wiki.sh`，把 `wiki/*.md` 镜像到 GitHub Wiki 的 `master` 分支。从 `wiki/` 删除的页面也会从 Wiki 中删除。它只需要内置的 `GITHUB_TOKEN`，写权限仅限于这一个任务。

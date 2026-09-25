# 测试

[English](Testing)

## 环境准备

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r tests/requirements.txt   # 固定版本的 Playwright + pytest
playwright install chromium
```

## 命令

```sh
./publish.sh --version 0.0.99                                   # 测试针对 dist/chrome 运行
CI=true pytest tests/test_extension.py -v                       # 完整测试
CI=true pytest tests/test_extension.py::TestOptionsPage::test_save_persists_config -v
CI=true pytest tests/test_extension.py -k TestContentScript -v  # 单个测试类
for f in src/*.js; do node --check "$f"; done                   # 语法检查
npx --yes web-ext@8.3.0 lint --source-dir dist/firefox --warnings-as-errors=false --self-hosted
python3 scripts/check-wiki.py wiki && bash scripts/test-wiki-publish.sh
```

测试会启动**有界面的** Chromium，因为无界面模式下扩展加载不稳定。CI 中用 `xvfb-run -a --server-args="-screen 0 1280x900x24"` 包裹 pytest。

## 测试覆盖范围

- `TestContentScript` 加载**打包后的** `content.js`，并用 `page.route` 在 `https://chatgpt.com/` 下提供仿真 ChatGPT 页面。夹具与 [架构](Architecture-zh-CN) 中的真实页面钩子一致，不含任何真实账号数据。
- 其他测试类覆盖设置页、设置迁移和导入/导出。
- `tests/unit_test.html` 只测试纯函数的副本，不测试真实的内容脚本。
- Firefox 在 CI 中只做静态检查，没有测试运行时行为。

## 实机测试规则

- 自动化运行时始终加 `CI=true`。否则测试会使用 `tests/.test-profile/`，里面保存着 ChatGPT 登录状态。绝不要删除它、复制它的 Cookie，或同时用它开两个浏览器。
- ChatGPT 的 Cookie 有效期很短：整个实机测试过程只用一个持久化浏览器上下文，并设置 `ignore_default_args=['--enable-automation', '--disable-extensions']`。
- 在 chatgpt.com 上只读：绝不发送、新建、重命名或删除会话。
- chatgpt.com 的 CSP 禁止 `unsafe-eval`。给 Playwright 的 `wait_for_function` 传**函数**而不是字符串；字符串条件会立即抛出 `EvalError`，被 `try/except` 吞掉后看起来像"超时"。
- 夹具测试通过不代表实机兼容；还要在 chatgpt.com 上检查真实扩展。

# canvas_pdf

一个面向上海交通大学课程平台 `https://*.sjtu.edu.cn/*` 的自动化项目，用来把课件缩略图自动收集、提交给本机服务下载原图，并在本地合成为高清 PDF。

当前仓库核心文件：

- `sjtu_slide_downloader.user.js`
- `local_pdf_service.py`
- `deepseek_client.py`
- `pdf_postprocess.py`
- `deepseek_selfcheck.py`
- `postprocess_selfcheck.py`
- `service_selfcheck.py`
- `start_local_pdf_service.bat`
- `selfcheck.js`

最后一次修复与文档整理日期：2026-04-02

## 1. 这个项目解决什么问题

很多课程页面会把课件以缩略图或图片流的形式展示出来，浏览体验还可以，但批量保存、整理和归档不方便。

这个脚本做的事情是：

1. 在课程页面右下角注入一个“下载高清 PDF”按钮。
2. 自动寻找课件缩略图容器。
3. 自动滚动容器，尽量触发懒加载。
4. 收集每一页课件图片地址。
5. 将任务发送给本机 `127.0.0.1` 上运行的 Python 服务。
6. 本地服务下载原始图片。
7. 本地服务用 Pillow 合成高清 PDF 并保存到本地目录。

## 2. 本次修复了什么

这次不是简单“改几行”，而是围绕稳定性做了一轮严格修复。

### 2.0 注入与单页应用兼容更稳

旧版脚本只匹配固定域名，而且默认按“整页刷新一次，脚本执行一次”的模型工作。

这在交大视频平台这类播放器式页面上不够稳，因为课程切换可能只是前端路由变化，而不是整页刷新。

现在的实现改为：

- `@match` 放宽到 `https://*.sjtu.edu.cn/*`，并兼容 `http://*.sjtu.edu.cn/*`
- 启用 `@grant window.onurlchange`
- 监听 `urlchange`、`history.pushState`、`history.replaceState`、`popstate`
- URL 变化后重新判断当前页面是不是课件页
- 如果离开课件页，会自动移除按钮

### 2.1 资源发现更稳

旧版实现只依赖：

- 固定容器选择器 `.ppt-card-wrapper__inner`
- 固定图片 URL 片段 `couresimg`

这种写法很脆弱。只要前端类名、懒加载字段、图片地址规则有一点变化，脚本就会直接失效。

现在的实现改为：

- 先尝试多个候选容器选择器
- 再根据“图片数量 + 是否可滚动 + 子元素数量”给候选容器打分
- 优先选最像“课件缩略图容器”的那个元素
- 收集图片地址时，同时兼容 `currentSrc`、`src`、`data-src`、`data-original`、`dataset.src` 等多个来源

### 2.2 懒加载等待更稳

旧版逻辑是：

- 横向滚动
- 固定等待 800ms
- 立刻开始抓图

问题是：如果网络慢，或者最后几页刚好还没完成懒加载，就会漏页。

现在的实现改为：

- 分步滚动容器
- 每步滚动后重新统计当前已发现图片
- 到达末尾后，不是立刻结束，而是等待图片集合稳定若干轮
- 只有当 URL 集合连续稳定后才进入导出阶段

### 2.3 本地高清合成更稳

旧版浏览器端直接 `jsPDF` 合成的问题：

- 页面失败时只是 `console.warn`
- 但仍然继续走“下载完成”提示
- 还可能留下空白页

现在的实现改为：

- 浏览器脚本只负责抓取 URL 和页序
- 本地 Python 服务负责下载原图
- 本地 Pillow 负责在本机合成 PDF
- 浏览器端不再承担最终高清 PDF 的重编码任务
- 服务端返回保存路径，便于确认结果

### 2.4 本地服务支持一条龙自动化

现在的实现新增：

- `GET /health` 用于检查本地服务是否已启动
- `POST /jobs` 用于提交下载与合成任务
- Windows 启动脚本 `start_local_pdf_service.bat`
- Python 自检脚本 `service_selfcheck.py`

### 2.5 DeepSeek 命名增强与页过滤

现在的实现支持一层可选的后处理：

- 如果设置了 `DEEPSEEK_API_KEY`，会调用 DeepSeek 官方聊天接口生成更合理的 PDF 文件名
- 本地服务会对下载后的图片页做图像特征分析
- 明显纯白、纯黑、桌面截图/照片风格的页会被尽量过滤掉

注意：

- DeepSeek 目前在这个项目里用于命名增强，不直接读取图片本身
- “删无内容页”当前主要依赖本地图像启发式，不是全靠模型判断

### 2.6 图片尺寸与格式更稳

旧版强行把所有图片都按：

- `1920 x 1080`
- `JPEG`

写进 PDF。

这会带来两个问题：

- 不是 16:9 的课件会被拉伸
- 不是 JPEG 的图片可能处理异常

现在的实现改为：

- 每页按实际图片尺寸创建页面
- 自动判断横向或纵向页面
- 按 MIME 类型或 URL 猜测图片格式
- 使用 `HTMLImageElement` 写入 PDF

### 2.7 文件名更稳

课件标题里经常包含：

- `/`
- `:`
- `?`
- `*`

这些字符会导致 Windows 文件名不合法。

现在会自动做文件名清洗，避免保存失败。

### 2.8 加了可重复执行的自动化自检

项目现在附带 `selfcheck.js`，可以在本地做一轮快速回归：

- 校验关键测试钩子是否存在
- 校验文件名清洗
- 校验图片 URL 收集与去重
- 校验容器识别逻辑
- 校验本地服务健康检查与任务提交逻辑
- 校验部分页面失败时的浏览器端兜底 PDF 生成逻辑

同时附带 `service_selfcheck.py`，用于验证本地 Pillow 合成流程。

## 3. 项目结构说明

### 3.1 `sjtu_slide_downloader.user.js`

这是主脚本，分成几类模块：

- UI 模块
  - `showToast`
  - `hideToast`
  - `setButtonBusy`
  - `createUi`

- 页面识别模块
  - `collectCandidateContainers`
  - `scoreContainer`
  - `findBestSlideContainer`
  - `getCourseTitle`

- 图片发现与懒加载模块
  - `normalizeUrl`
  - `isUsableImageUrl`
  - `getImageCandidateUrl`
  - `collectSlideImageUrls`
  - `waitForThumbnailSettle`
  - `scrollToLoadAll`

- 图片加载与 PDF 生成模块
  - `fetchImageBlob`
  - `loadImageFromSrc`
  - `fetchRenderableImage`
  - `generatePDF`

- 启动与总流程模块
  - `handleDownload`
  - `bootstrap`

### 3.2 `selfcheck.js`

这是无依赖的本地自检脚本。它不会真的打开浏览器，而是：

- 用 Node 读入 userscript 源码
- 构造一个最小可运行的浏览器/GM/mock 环境
- 用假数据模拟成功与失败的下载场景
- 检查返回结果是否符合预期

### 3.3 `local_pdf_service.py`

这是本地高清 PDF 服务，负责：

- 提供 `GET /health`
- 提供 `POST /jobs`
- 下载原始课件图片
- 使用 Pillow 合成本地高清 PDF

### 3.4 `service_selfcheck.py`

这是 Python 侧自检脚本，会生成两张测试图片并验证 PDF 合成。

### 3.5 `start_local_pdf_service.bat`

这是 Windows 一键启动入口，双击即可启动本地服务。

### 3.6 `deepseek_client.py`

这是 DeepSeek API 客户端，负责：

- 读取 `DEEPSEEK_API_KEY`
- 按官方 `/chat/completions` 接口发请求
- 使用 JSON 输出模式解析返回结果

### 3.7 `pdf_postprocess.py`

这是 PDF 后处理模块，负责：

- 分析每页图像的白底比例、颜色丰富度、边缘密度
- 尽量过滤纯白页、纯黑页、桌面/照片风格页
- 调用 DeepSeek 生成更合理的标题建议

## 4. 安装方法

## 4.1 浏览器环境

推荐：

- Chrome / Edge
- Tampermonkey 扩展

## 4.2 安装脚本

1. 安装 Tampermonkey。
2. 打开 Tampermonkey 新建脚本页面。
3. 将 `sjtu_slide_downloader.user.js` 全部内容粘贴进去并保存。
4. 如需启用 DeepSeek 命名增强，先设置环境变量 `DEEPSEEK_API_KEY`。
5. 双击运行 `start_local_pdf_service.bat`，或在项目目录执行 `python local_pdf_service.py`。
6. 打开 `https://*.sjtu.edu.cn/*` 下的相关课程页面。
7. 在课件页右下角点击“下载高清 PDF”。

## 4.3 运行前提

需要确保：

- 课程页面已经打开
- 课件缩略图区域已经渲染出来
- 浏览器没有阻止脚本运行
- Tampermonkey 已启用当前脚本
- 本地服务已经启动
- 若要启用命名增强，`DEEPSEEK_API_KEY` 已设置

## 5. 本地开发与自检

## 5.1 语法检查

在项目目录运行：

```powershell
node --check sjtu_slide_downloader.user.js
node --check selfcheck.js
python -m py_compile deepseek_client.py pdf_postprocess.py deepseek_selfcheck.py postprocess_selfcheck.py
python -m py_compile local_pdf_service.py service_selfcheck.py
```

## 5.2 自动化自检

```powershell
node selfcheck.js
python deepseek_selfcheck.py
python postprocess_selfcheck.py
python service_selfcheck.py
```

期望输出：

```text
selfcheck passed
deepseek selfcheck passed
postprocess selfcheck passed
service selfcheck passed
```

说明：

- 自检过程中会故意模拟“第二页下载失败”的场景
- 控制台出现该失败日志是预期行为
- 只要最终输出 `selfcheck passed`，说明当前核心逻辑符合断言
- `deepseek selfcheck passed` 表示 DeepSeek 客户端解析逻辑正常
- `postprocess selfcheck passed` 表示页过滤与命名回退逻辑正常
- `service selfcheck passed` 表示本地 Pillow 合成链路正常

## 5.3 我这次实际做过的检查

已实际执行：

```powershell
node --check sjtu_slide_downloader.user.js
node --check selfcheck.js
node selfcheck.js
python -m py_compile deepseek_client.py pdf_postprocess.py deepseek_selfcheck.py postprocess_selfcheck.py
python deepseek_selfcheck.py
python postprocess_selfcheck.py
python -m py_compile local_pdf_service.py service_selfcheck.py
python service_selfcheck.py
```

结果：

- JS 与 Python 文件均通过语法检查
- 浏览器脚本自检通过
- DeepSeek 客户端与后处理模块自检通过
- 本地服务自检通过

## 6. 核心工作原理

## 6.1 为什么不用页面里现成的截图直接拼

因为页面里的缩略图可能有：

- 懒加载
- 占位图
- 数据地址不在 `src`
- 跨域访问限制

所以脚本需要先做“真正图片地址发现”，不能只扫一遍 `img.src` 就结束。

## 6.2 为什么还要用 `GM_xmlhttpRequest`

普通页面脚本直接请求跨域图片时，经常会碰到 CORS 问题。

Tampermonkey 提供的 `GM_xmlhttpRequest` 可以在声明了 `@connect` 后更稳定地获取跨域资源，这就是这里保留它的原因。

## 6.3 为什么要引入本地服务

浏览器端直接合成 PDF 有两个天然问题：

- 图片可能被再次压缩或重编码
- 大课件在浏览器内存里处理不稳定

本项目现在把高清 PDF 合成挪到本地 Python 服务：

1. 浏览器负责抓课件图片 URL 和页序。
2. 本地服务下载原始图片。
3. Pillow 在本机合成 PDF。

这样更接近“原图下载后再本地整理”的流程，质量和稳定性都更好。当前默认导出目录是 `E:\zhiwang_text\canvas_course`。

## 6.4 为什么保留浏览器端图片处理逻辑

项目里仍保留了一部分浏览器端图片处理与自检代码，原因有两个：

- 这部分逻辑仍用于发现页面里的真实课件图片 URL
- 现有自动化自检依赖这些函数验证顺序、失败路径和兼容性

## 6.5 DeepSeek 在当前方案里具体做什么

当前 DeepSeek 接入方式是：

1. 本地服务先下载课件图片。
2. 本地图像启发式先过滤明显无内容页。
3. 再把标题、来源 URL、页分析摘要交给 DeepSeek。
4. DeepSeek 返回更适合保存的标题建议。

这样设计的原因是：

- 官方文档当前明确提供的是文本聊天接口
- 项目无需依赖额外 OCR 或视觉模型才能先跑通
- 删页逻辑保持在本地，速度更快，也不依赖外部 API

## 7. 常见问题排查

### 7.1 页面上没有按钮

检查：

- Tampermonkey 是否启用
- 当前 URL 是否匹配 `https://*.sjtu.edu.cn/*`
- 页面是否完整加载
- 浏览器控制台是否有 userscript 报错

### 7.2 提示“未找到课件图片”

可能原因：

- 当前页面不是课件预览页
- 站点结构发生变化
- 缩略图尚未渲染完成
- 页面使用了新的懒加载字段或新的容器结构

建议：

- 先手动滚动一下课件区域再重试
- 打开浏览器开发者工具，检查课件区域里的真实 `img` 地址
- 如站点结构已改动，重点检查 `findBestSlideContainer` 和 `getImageCandidateUrl`

### 7.3 只导出了一部分页面

常见原因：

- 某些图片下载失败
- 站点返回了临时失效链接
- 最后几页图片仍未出现

现在脚本会把任务发给本地服务。若合成结果页数不完整，优先检查本地服务终端输出和浏览器控制台日志。

### 7.4 下载的文件名不对

脚本目前通过页面标题区域获取名称，并做文件名清洗。

如果站点标题结构变化，需要检查：

- `TITLE_SELECTORS`
- `getCourseTitle`

### 7.5 本地 PDF 保存到哪里

当前默认输出目录是：

```text
E:\zhiwang_text\canvas_course
```

本地服务会直接把最终 PDF 保存到这个目录下。

### 7.6 如何启用 DeepSeek 命名增强

Windows `cmd` 示例：

```cmd
set DEEPSEEK_API_KEY=你的密钥
cd /d E:\claude_ask\canvas_pdf
python local_pdf_service.py
```

如果不设置 `DEEPSEEK_API_KEY`：

- 本地服务仍然可以正常工作
- 只是会跳过 DeepSeek 命名增强
- 文件名会退回到浏览器传来的原标题

### 7.7 Tampermonkey 明明启用了但脚本偶发不执行

如果你发现：

- 探针脚本有时执行
- 正式脚本有时不执行
- Tampermonkey 菜单显示启用，但页面里没有注入

优先按下面步骤恢复，不要只点扩展图标里的开关：

1. 打开 `chrome://extensions/`
2. 找到 Tampermonkey 扩展
3. 将扩展整体关闭
4. 再将扩展整体开启
5. 关闭旧课程标签页
6. 新开课程页面再试

根据实测，这种方式比只在工具栏菜单里切换脚本开关更稳定。

## 8. 维护建议

如果后面学校平台改版，优先检查下面三类地方：

1. 课件缩略图容器的 DOM 结构是否变化。
2. 图片真实地址是否还在 `src/currentSrc/data-*` 中。
3. 图片是否仍然能通过 `GM_xmlhttpRequest` 获取。

最容易失效的函数通常是：

- `findBestSlideContainer`
- `getImageCandidateUrl`
- `collectSlideImageUrls`

## 9. 联网交叉验证记录

本次修复时，已对照官方文档核验以下点：

- Tampermonkey 官方文档
  - `@match` 支持子域名通配写法，如 `https://*.sjtu.edu.cn/*`
  - `GM_xmlhttpRequest(details)` 可用于受控网络请求
  - `@connect` 支持配置允许连接的域名，`*` 可作为兜底
- Python 官方文档
  - `http.server` 可快速提供本地 HTTP 服务
- Pillow 官方文档
  - `Image.save(..., save_all=True, append_images=...)` 可将多张图片合成为 PDF

建议优先参考这些官方文档：

- Tampermonkey: https://www.tampermonkey.net/documentation.php
- Python `http.server`: https://docs.python.org/3/library/http.server.html
- Pillow Image: https://pillow.readthedocs.io/en/stable/reference/Image.html

## 10. GitHub 同步

如果你要把当前目录推到 GitHub 仓库：

```powershell
git init
git branch -M main
git remote add origin https://github.com/wuyutanhongyuxin-cell/canvas_pdf.git
git add .
git commit -m "fix: harden userscript and add README/selfcheck"
git push -u origin main
```

如果远端已经有内容，建议先拉取或直接克隆远端仓库后再覆盖文件，避免历史冲突。

## 11. 后续可继续增强的方向

可以继续做，但这次没有强行加入，以免引入新变量：

- 导出前显示一个预览统计面板
- 支持选择页面范围
- 支持失败页重试
- 支持把失败页列表写入日志文件
- 支持更细粒度的站点 DOM 适配器

## 12. 总结

当前版本相较于原始实现，重点不是“功能更多”，而是“成功路径更真实、失败路径更诚实、后续维护更容易”。

如果你后面还要继续维护这个脚本，最值得长期保留的两样东西是：

- 自动化自检脚本 `selfcheck.js`
- 这份 README 里的设计说明与排障思路

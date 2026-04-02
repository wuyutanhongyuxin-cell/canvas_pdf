# canvas_pdf

一个面向上海交通大学课程平台 `https://v.sjtu.edu.cn/` 的 userscript 项目，用来把课件缩略图自动收集、下载并合成为 PDF。

当前仓库核心文件：

- `sjtu_slide_downloader.user.js`
- `selfcheck.js`

最后一次修复与文档整理日期：2026-04-02

## 1. 这个项目解决什么问题

很多课程页面会把课件以缩略图或图片流的形式展示出来，浏览体验还可以，但批量保存、整理和归档不方便。

这个脚本做的事情是：

1. 在课程页面右下角注入一个“下载课件 PDF”按钮。
2. 自动寻找课件缩略图容器。
3. 自动滚动容器，尽量触发懒加载。
4. 收集每一页课件图片地址。
5. 逐页拉取图片。
6. 使用 `jsPDF` 把成功下载的页面写入 PDF。
7. 自动下载生成好的 PDF 文件。

## 2. 本次修复了什么

这次不是简单“改几行”，而是围绕稳定性做了一轮严格修复。

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

### 2.3 PDF 生成更稳

旧版实现的问题：

- 页面失败时只是 `console.warn`
- 但仍然继续走“下载完成”提示
- 还可能留下空白页

现在的实现改为：

- 每一页单独拉取并单独解码
- 只有图片真正成功加载后，才写进 PDF
- 部分失败时，不再制造空白页
- 全部失败时，直接抛错，不生成伪成功 PDF
- 最终会返回成功页数和失败页数

### 2.4 图片尺寸与格式更稳

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

### 2.5 文件名更稳

课件标题里经常包含：

- `/`
- `:`
- `?`
- `*`

这些字符会导致 Windows 文件名不合法。

现在会自动做文件名清洗，避免保存失败。

### 2.6 加了可重复执行的自动化自检

项目现在附带 `selfcheck.js`，可以在本地做一轮快速回归：

- 校验关键测试钩子是否存在
- 校验文件名清洗
- 校验图片 URL 收集与去重
- 校验容器识别逻辑
- 校验部分页面失败时的 PDF 生成逻辑
- 校验 `px_scaling` 热修复是否启用

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

## 4. 安装方法

## 4.1 浏览器环境

推荐：

- Chrome / Edge
- Tampermonkey 扩展

## 4.2 安装脚本

1. 安装 Tampermonkey。
2. 打开 Tampermonkey 新建脚本页面。
3. 将 `sjtu_slide_downloader.user.js` 全部内容粘贴进去并保存。
4. 打开 `https://v.sjtu.edu.cn/` 相关课程页面。
5. 在课件页右下角点击“下载课件 PDF”。

## 4.3 运行前提

需要确保：

- 课程页面已经打开
- 课件缩略图区域已经渲染出来
- 浏览器没有阻止脚本运行
- Tampermonkey 已启用当前脚本

## 5. 本地开发与自检

## 5.1 语法检查

在项目目录运行：

```powershell
node --check sjtu_slide_downloader.user.js
node --check selfcheck.js
```

## 5.2 自动化自检

```powershell
node selfcheck.js
```

期望输出：

```text
selfcheck passed
```

说明：

- 自检过程中会故意模拟“第二页下载失败”的场景
- 控制台出现该失败日志是预期行为
- 只要最终输出 `selfcheck passed`，说明当前核心逻辑符合断言

## 5.3 我这次实际做过的检查

已实际执行：

```powershell
node --check sjtu_slide_downloader.user.js
node --check selfcheck.js
node selfcheck.js
```

结果：

- 两个文件均通过语法检查
- 自动化自检通过

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

## 6.3 为什么启用 `px_scaling`

脚本使用 `jsPDF` 的 `px` 单位按图片像素尺寸生成页面。

根据 jsPDF 官方文档，如果使用 `px` 单位，需要启用：

```js
hotfixes: ['px_scaling']
```

否则页面尺寸可能缩放不正确。

## 6.4 为什么改成“成功一页写一页”

这是为了避免：

- 先加页，再发现图片下载失败
- 最终 PDF 里出现空白页

现在的顺序是：

1. 先拉图
2. 再解码
3. 确认成功后才写入 PDF

这样失败页不会污染最终文件。

## 7. 常见问题排查

### 7.1 页面上没有按钮

检查：

- Tampermonkey 是否启用
- 当前 URL 是否匹配 `https://v.sjtu.edu.cn/*`
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

现在脚本会在 toast 中提示成功页数和失败页数，详细失败信息会输出到控制台。

### 7.4 下载的文件名不对

脚本目前通过页面标题区域获取名称，并做文件名清洗。

如果站点标题结构变化，需要检查：

- `TITLE_SELECTORS`
- `getCourseTitle`

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
  - `GM_xmlhttpRequest(details)` 可用于受控网络请求
  - `@connect` 支持配置允许连接的域名，`*` 可作为兜底

- jsPDF 官方文档
  - `jsPDF` 在使用 `unit: 'px'` 时应启用 `hotfixes: ['px_scaling']`
  - `addImage` 支持 `HTMLImageElement`
  - `addPage` 支持自定义页面尺寸

- MDN 官方文档
  - `HTMLImageElement.decode()` 返回 Promise，可用于在图片解码完成后再继续处理

建议优先参考这些官方文档：

- Tampermonkey: https://www.tampermonkey.net/documentation.php
- jsPDF: https://parallax.github.io/jsPDF/docs/jsPDF.html
- jsPDF addImage: https://parallax.github.io/jsPDF/docs/module-addImage.html#~addImage
- MDN decode: https://developer.mozilla.org/en-US/docs/Web/API/HTMLImageElement/decode

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

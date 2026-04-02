# Canvas PDF

一个面向上海交通大学课堂页面的课件导出工具。

它的目标很简单：
- 在课程页里自动抓取 PPT 缩略图对应的原始图片
- 交给本地 Python 服务下载并合成为高清 PDF
- 尽量过滤明显无内容的页面
- 在可用时用 DeepSeek 做命名增强

当前默认输出目录：

```text
E:\zhiwang_text\canvas_course
```

## 轻盈架构

整个项目只分成三层，尽量克制，不做多余设计。

### 1. 浏览器层

文件：
- `sjtu_slide_downloader.user.js`

职责：
- 在 SJTU 课程页面注入“下载高清 PDF”按钮
- 识别当前课件缩略图区
- 收集图片 URL
- 提交任务到本地服务 `http://127.0.0.1:38765`

### 2. 本地服务层

文件：
- `local_pdf_service.py`
- `start_local_pdf_service.bat`

职责：
- 提供 `/health` 和 `/jobs`
- 下载原始课件图片
- 合成高清 PDF
- 保存到本地目录

### 3. 后处理层

文件：
- `pdf_postprocess.py`
- `deepseek_client.py`

职责：
- 过滤明显无内容页面
- 尽量删除桌面壁纸类页面
- 保留有实际课件内容的 PowerPoint 编辑界面页
- 可选调用 DeepSeek 生成更自然的文件名

## 快速启动

### 1. 安装浏览器脚本

准备：
- Chrome 或 Edge
- Tampermonkey

步骤：
1. 打开 Tampermonkey，新建脚本。
2. 将 `sjtu_slide_downloader.user.js` 全部内容粘贴进去并保存。
3. 确保 Chrome 扩展详情页里已经开启“允许运行用户脚本”。

### 2. 配置 DeepSeek，可选

如果你想启用命名增强，在项目目录创建 `.env`：

```text
DEEPSEEK_API_KEY=你的DeepSeek密钥
```

也可以直接复制模板：

```cmd
cd /d E:\claude_ask\canvas_pdf
copy .env.example .env
notepad .env
```

如果不配置 `.env`，项目仍然可以正常导出 PDF，只是文件名会回退到本地规则。

### 3. 启动本地服务

二选一：

```cmd
cd /d E:\claude_ask\canvas_pdf
python local_pdf_service.py
```

或直接双击：

```text
start_local_pdf_service.bat
```

启动成功后，终端应看到：

```text
[local-pdf-service] listening on http://127.0.0.1:38765
[local-pdf-service] output dir: E:\zhiwang_text\canvas_course
```

### 4. 开始导出

1. 打开交大课程页面。
2. 等 PPT 缩略图区加载出来。
3. 点击右下角“下载高清 PDF”。
4. 保持页面和本地服务窗口不要关闭，等待任务完成。

## 文件输出规则

### PDF 保存位置

默认保存在：

```text
E:\zhiwang_text\canvas_course
```

### 重名处理

不会覆盖旧文件。

示例：
- `PPT.pdf`
- `PPT_2.pdf`
- `PPT_3.pdf`

### 命名来源

优先级如下：
1. 当前课程标题
2. 当前选中的讲次标签
3. DeepSeek 命名增强
4. 本地回退命名

如果 DeepSeek 不可用，仍会生成一个稳定可用的本地文件名。

## 重要注意事项

### 1. 本地服务必须一直开着

导出期间不要关闭运行 `local_pdf_service.py` 的窗口。

### 2. 长任务需要等待

课件页多的时候，`/jobs` 处理可能持续几分钟。  
当前前端等待时间已经放宽到 10 分钟，不要在中途关闭页面。

### 3. Tampermonkey 偶发不执行时

如果脚本明明启用了，但页面里没有按钮，优先这样恢复：

1. 打开 `chrome://extensions/`
2. 找到 Tampermonkey
3. 关闭整个扩展
4. 再重新开启
5. 关闭旧课程标签页
6. 新开课程页再试

不要只在工具栏里切脚本开关，这种恢复方式不稳定。

### 4. 页过滤不是“删除所有截图页”

当前策略是：
- 删除明显空白页、纯黑页、桌面壁纸页
- 保留有真实课件内容的编辑界面页

也就是说，像 PowerPoint 编辑界面但中间确实有课件正文的页，会被保留。

### 5. DeepSeek 只做命名增强

DeepSeek 当前不直接读取 PDF 图片内容做视觉理解。  
它主要用于在可用时把文件名整理得更自然。

### 6. `.env` 不要提交到 GitHub

`.env` 只应保留在本地。  
仓库里只保留 `.env.example`。

## 快速排障

### 页面上没有按钮

检查：
- Tampermonkey 是否启用
- 用户脚本权限是否开启
- 当前页面是否是 `*.sjtu.edu.cn`
- 课程页是否已经完整加载

### 提示本地服务未运行

先确认你真的在项目目录启动了服务：

```cmd
cd /d E:\claude_ask\canvas_pdf
python local_pdf_service.py
```

再确认终端里能看到：

```text
[local-pdf-service] listening on http://127.0.0.1:38765
```

### 命名不准确

当前命名优先依赖：
- 当前课程标题
- 当前选中的“第 XX 讲”
- DeepSeek 命名增强

如果页面本身标题很弱，或站点结构变化，命名准确率会下降。

### 导出的页数不对

优先看本地服务窗口输出。  
如果站点图片链接临时失效，或页面缩略图尚未加载完整，结果页数会受影响。

## 自检命令

如果你在维护这个仓库，常用自检命令如下：

```cmd
cd /d E:\claude_ask\canvas_pdf
node --check sjtu_slide_downloader.user.js
node selfcheck.js
python -m py_compile local_pdf_service.py pdf_postprocess.py deepseek_client.py
python postprocess_selfcheck.py
python service_selfcheck.py
```

期望输出里至少包含：

```text
selfcheck passed
postprocess selfcheck passed
service selfcheck passed
```

## 文件一览

核心文件：
- `sjtu_slide_downloader.user.js`
- `local_pdf_service.py`
- `pdf_postprocess.py`
- `deepseek_client.py`
- `start_local_pdf_service.bat`
- `.env.example`

辅助自检：
- `selfcheck.js`
- `postprocess_selfcheck.py`
- `service_selfcheck.py`
- `deepseek_selfcheck.py`

---

这个 README 刻意写得很短。  
真正需要记住的只有一句话：

先启动本地服务，再去课程页点“下载高清 PDF”。

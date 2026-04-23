# Canvas PDF

一个面向上海交通大学课堂页面的课件导出工具。

它的目标很简单：
- 在课程页里自动抓取 PPT 缩略图对应的原始图片
- 交给本地 Python 服务下载并合成为高清 PDF
- 尽量过滤明显无内容的页面
- 在可用时用 DeepSeek 做命名增强

当前示例默认输出目录：

```text
E:\zhiwang_text\canvas_course
```

如果你交付给别人使用，建议按下面“PDF 保存位置”里的方式改成他们自己的目录。

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

## 客户电脑首次部署（严格 CMD 教程）

> 适用场景：在客户的 Windows 10 / 11 电脑上**第一次**安装本工具。  
> 全程在 **cmd**（不是 PowerShell）里执行，按顺序一条条来，不要跳步。

### 步骤 0｜确认系统

打开开始菜单 → 输入 `cmd` → 回车，弹出黑色窗口后执行：

```cmd
ver
```

要求是 Windows 10 或 Windows 11。

### 步骤 1｜安装 Python 3.10+

1. 浏览器打开 <https://www.python.org/downloads/windows/>
2. 下载 Python 3.10 或更高版本的 **Windows installer (64-bit)**
3. 双击安装时**务必勾选**底部的 `Add python.exe to PATH`，再点 Install Now
4. 安装结束后**关掉所有旧 cmd**，重新打开一个新 cmd 窗口（PATH 才会生效），执行：

```cmd
python --version
pip --version
```

期望输出（版本不低于 3.10 即可）：

```text
Python 3.11.x
pip 24.x from ...
```

如果提示 `'python' 不是内部或外部命令`，说明 PATH 没加上：重新运行 Python installer，选 Modify → 勾上 `Add Python to environment variables` → 应用。

### 步骤 2｜放置项目文件

把整个 `canvas_pdf` 项目文件夹拷到客户电脑一个固定位置，建议：

```text
E:\claude_ask\canvas_pdf
```

> 路径**不要含空格和中文符号**，否则 bat 启动会出问题。

进入目录确认文件齐全：

```cmd
cd /d E:\claude_ask\canvas_pdf
dir
```

至少要看到：

```text
local_pdf_service.py
sjtu_slide_downloader.user.js
pdf_postprocess.py
deepseek_client.py
start_local_pdf_service.bat
requirements.txt
```

### 步骤 3｜安装 Python 依赖

```cmd
cd /d E:\claude_ask\canvas_pdf
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

如果客户网络访问 pypi.org 慢或超时，临时换清华源：

```cmd
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

验证依赖装好了：

```cmd
python -c "import requests, PIL; print('deps ok')"
```

期望输出一行：

```text
deps ok
```

### 步骤 4｜准备输出目录

默认 PDF 写到 `E:\zhiwang_text\canvas_course`。如果客户机没有 E 盘或要换位置，按下文“PDF 保存位置”那一节改 `DEFAULT_OUTPUT_DIR`。

提前手动建好这个目录，避免首次写入失败：

```cmd
mkdir E:\zhiwang_text\canvas_course 2>nul
```

（换路径就把这里也改成对应的目录。）

### 步骤 5｜装浏览器脚本

1. 在 Chrome 或 Edge 装 Tampermonkey 扩展
2. 点 Tampermonkey 图标 → “管理面板” → “+” 新建脚本
3. 用记事本打开 `E:\claude_ask\canvas_pdf\sjtu_slide_downloader.user.js`，**全选复制**
4. 粘贴到 Tampermonkey 的编辑器，覆盖默认模板，按 Ctrl+S 保存
5. 浏览器地址栏访问 `chrome://extensions/`，找到 Tampermonkey → “详情” → 打开
   - “允许访问文件网址”
   - “允许用户脚本”

### 步骤 6｜（可选）配置 DeepSeek

要启用 AI 命名增强：

```cmd
cd /d E:\claude_ask\canvas_pdf
notepad .env
```

写入一行后保存：

```text
DEEPSEEK_API_KEY=sk-你的真实密钥
```

不配置也能正常出 PDF，命名走本地回退规则。

### 步骤 7｜首次启动并验证

开一个 cmd 窗口启动服务：

```cmd
cd /d E:\claude_ask\canvas_pdf
python local_pdf_service.py
```

或者直接双击：

```text
E:\claude_ask\canvas_pdf\start_local_pdf_service.bat
```

启动成功的标志是窗口里出现两行：

```text
[local-pdf-service] listening on http://127.0.0.1:38765
[local-pdf-service] output dir: E:\zhiwang_text\canvas_course
```

**这个 cmd 窗口在使用期间不能关。**

再开**另一个** cmd 做健康检查：

```cmd
curl http://127.0.0.1:38765/health
```

期望返回（字段顺序可能不同）：

```text
{"ok": true, ...}
```

如果 curl 报 `Failed to connect` / 超时，说明服务没起来，回服务窗口看错误信息。

### 步骤 8｜跑一次完整流程

1. 浏览器打开任一交大课程页面
2. 等 PPT 缩略图区加载完毕
3. 页面右下角出现“下载高清 PDF”按钮 → 点击
4. 弹出“输入子文件夹名称”时，可填课程或讲次名（留空就走默认目录）
5. 等任务完成。页数多时可能持续几分钟，期间**不要关浏览器、不要关服务窗口**
6. 完成后到输出目录确认 PDF 存在

### 步骤 9｜以后每天怎么用

部署完成后，客户日常只需要两步：

1. 双击 `start_local_pdf_service.bat`，等到出现 `listening on http://127.0.0.1:38765`
2. 浏览器打开课程页 → 点“下载高清 PDF”

### 部署期常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| `'python' 不是内部或外部命令` | 安装时没勾 Add to PATH | 重装 Python 并勾选；或手动把 Python 安装目录加到系统 PATH，重开 cmd |
| `pip install` 报 SSL / 超时 | 客户网络限速或被墙 | 改用清华源 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| 服务窗口一闪而过 | 缺依赖 / 端口占用 | 不要双击 bat，改用 cmd 启动 `python local_pdf_service.py` 看完整报错 |
| 端口 38765 被占用 | 之前的服务没退干净 | 任务管理器结束 python.exe 后重启，或重启电脑 |
| `curl /health` 连不上 | 服务未起 / 本地防火墙拦回环 | 先看服务窗口日志；必要时在 Windows 防火墙放行 `127.0.0.1:38765` |
| 课程页没有按钮 | Tampermonkey 没启用 / 页面没加载完 | 详见下文“快速排障” |
| 单张图片下载失败 | 客户网络抖动 | 工具自带 3 次重试 + 退避；反复失败就换网络重试整个任务 |

## 文件输出规则

### PDF 保存位置

当前仓库里的示例默认路径是：

```text
E:\zhiwang_text\canvas_course
```

这不是固定要求，可以改。

如果你是面向客户交付，推荐用下面两种方式之一：

方式一：启动时临时指定输出目录

```cmd
cd /d E:\claude_ask\canvas_pdf
python local_pdf_service.py --output-dir "D:\Canvas PDF"
```

方式二：直接修改默认路径

打开 [local_pdf_service.py](/E:/claude_ask/canvas_pdf/local_pdf_service.py)，找到：

```python
DEFAULT_OUTPUT_DIR = Path(r"E:\zhiwang_text\canvas_course")
```

改成客户自己的目录，例如：

```python
DEFAULT_OUTPUT_DIR = Path(r"D:\Canvas PDF")
```

改完后重启本地服务即可。

小建议：
- 路径尽量用纯英文或常见中文目录
- 不要放到权限很严格的系统目录
- 给客户时最好提前帮他们改好，不要让他们自己找代码

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

## 打开即用：纯网页版

**这一版最大的变化：不用再下载任何东西了。**

### 👉 https://ba4ihb.github.io/ADIF-2-XLSX/web.html

打开网页就能转换。不需要下载、不需要安装、不需要跑任何本地程序。
把 `.adi` 拖进页面 → 选好列 → 点「开始转换」→ Excel 直接下载。

它通过 **Pyodide**（CPython 编译成 WebAssembly）把**同一份 `src/adif2xlsx.py`
跑在页面里** —— 所以网页版和桌面版是同一个转换器，不是用 JavaScript 重写的第二份。
**转换在你的浏览器内完成，日志不上传、不联网、没有服务器。**
首次打开下载约 10 MB 运行时，之后浏览器缓存，秒开。

---

## 下载（备选）

不想等那 10 MB，或者网络不便？下面这些**解压即用，不需要装 Python**。

三种界面**功能完全一致**（同一份转换代码，输出逐单元格相同）：

| 下载 | 界面 | 解压后双击 |
|------|------|-----------|
| `adif2xlsx-web-v1.1.0.zip` | 本机服务版（浏览器界面） | `启动网页版.bat` |
| `adif2xlsx-ui-v1.1.0.zip` | 桌面窗口版 | `adif2xlsx-ui.exe` |
| `adif2xlsx-cli-v1.1.0.zip` | 命令行版 | 终端里调用 `adif2xlsx.exe` |

每个界面另有 `-onedir` 文件夹版：**启动明显更快**，日常建议选它。
`adif2xlsx-all-v1.1.0.zip` 一次包含全部六种构建，方便自己挑。

> **单文件版启动慢**（约 8–60 秒，要解压到临时目录）。文件夹版快得多。

---

## v1.1.0 做了什么

### 新增：真正的纯网页版（见上）

### 修复：DXCC 前缀歧义被静默判错

ARRL 官方列表把**同一个前缀同时给多个实体**，而且**不说明哪个呼号区归谁** ——
`CE0` 给了复活节岛、胡安·费尔南德斯、圣费利克斯和圣安布罗西奥**三个**，
`FO`/`TX` 给了**四个**，`TO` 给了**七个**，全表共 **56 个**这样的前缀。

之前用 `setdefault` 建表，**谁先读到谁占**，结果：

| 呼号 | 应该是 | 之前判成 |
|------|--------|---------|
| `CE0Z`（胡安·费尔南德斯） | 胡安·费尔南德斯群岛 | ❌ 复活节岛 |
| `CE0X`（圣费利克斯） | 圣费利克斯和圣安布罗西奥 | ❌ 复活节岛 |

一次查表只能返回一个实体，所以**必须选一个 —— 但不能悄悄选**。
现在 `DXCC_SOURCE` 列会把其它可能写出来：

```text
CE0Z   → 复活节岛    PREFIX (CE0 shared with Juan Fernandez Is., San Felix & San Ambrosio)
VK0AA  → 赫德岛      PREFIX (VK0 shared with Macquarie I.)
3D2AA  → 斐济        PREFIX (3D2 shared with Rotuma I., Conway Reef)
```

遇到稀有岛屿，你看到的是「**这可能是复活节岛，也可能是胡安·费尔南德斯**」，
而不是一个毫无提示的错误答案。

> **要确定答案，请让日志写入 `DXCC` 编号或 `COUNTRY`** —— 它们永远优先于前缀。
> LoTW、Club Log、N1MM 都会写 `DXCC`。

### 文档：中英文拆成两个文件

原来的 README 是「中文写一半，后面接一份英文文档」。现在：

- **[README.md](https://github.com/ba4ihb/ADIF-2-XLSX/blob/main/README.md)** — 简体中文
- **[README.en.md](https://github.com/ba4ihb/ADIF-2-XLSX/blob/main/README.en.md)** — English

两个文件顶部和底部都有语言切换链接，各自只有一种语言。
并加上了**语言百分比徽章**（Python 84.8 % · HTML 15.0 % · Batchfile 0.2 %）。

### 其他修复

- **Windows 控制台崩溃**：列名是中文，在 cp1252 控制台上 `print()` 会抛
  `UnicodeEncodeError` —— **文件已经写成功，进程却报崩溃**。现在统一转 UTF-8。
- **`emit()` 的兜底漏了 `UnicodeEncodeError`**：它自称「尽力而为」，
  却没接住控制台唯一真正会抛的异常。
- **CI 之前一直失败**：现已修复并在 **Windows + Linux × Python 3.10 + 3.12**
  四个组合上全绿（见顶部徽章）。顺带查出测试里 4 处写死了本机绝对路径。

---

## 核心功能

- 保留原始数据，**自动识别 ADIF 字段**（不硬编码字段列表）
- 某列在所有记录中均为空则**不输出该列**
- **必选列 9 个**，永远输出：`CALL` `QSO_DATE` `TIME_ON_UTC` `FREQ_MHZ`
  `BAND` `MODE` `RST_SENT` `RST_RCVD` `STATION_CALLSIGN`
  （另有自动生成的 `SOURCE_FILE` `DXCC_ENTITY` `QSL_POSTAGE_AIR`）
- **所有时间为 UTC，不做时区换算**，并在列名与表头写明
- **DXCC 实体判定**（≠ 国家：中国含港澳台、俄罗斯分欧亚、美国分本土/夏威夷/阿拉斯加…），
  表由 **ARRL 官方 DXCC 列表（2026 年 1 月版，340 个实体）** 生成
- **QSL 平信邮资**（中国邮政 20 克信函）：只显示信函价格，不提供明信片价格；
  340 个实体全部有答案（302 个给价，38 个明确写「不通邮」）；
  价格同时标注**生效日期与核对日期**
- `Summary` 表**第 1 行**写明数据来源与「单元格为空」的含义

---

## 校验

```bat
certutil -hashfile adif2xlsx-web-v1.1.0.zip SHA256
```

与 `SHA256SUMS.txt` 对照即可。

## 隐私

转换**不联网、不上传**。浏览器版全程在页面内完成，没有后端。
测试用日志为**合成假呼号**，与真实导出**零重叠**（已脚本核对），
不含机主呼号、姓名、地址、邮箱、真实网格坐标。

---

**本项目全部代码、测试与文档由 DeepSeek Harness + DeepSeek-V4.1-Flash Max 编写。**

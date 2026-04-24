# SoftwareUsageMeter 变更摘要

## 2026-04-24 交付稳定性更新

本轮更新来自第二次远程交付后的问题复盘，并已在另一台 Windows 电脑上做兼容性测试，暂未发现明显异常。

### 1. 启动提示与壁纸

- `SoftwareUsageMeter.exe` 启动后会显示友好提示窗，说明程序已启动并正在等待像素蛋糕。
- 提示窗支持读取管理后台配置的壁纸，未配置时使用浅色兜底背景。
- 提示窗为非阻塞窗口，数秒后自动关闭，不影响后台监控启动。

### 2. 计时开始条件收紧

- 只有检测到可见、尺寸合理、标题有效的像素蛋糕主窗口后才开始计时。
- 仅存在后台残留进程、离屏窗口或异常最小化窗口时，不会提前计费。
- 像素蛋糕退出后，本轮计时直接结束并清零；再次启动像素蛋糕从 0 开始。

### 3. 收款后恢复与二次弹窗保护

- 进程挂起逻辑已做幂等处理，避免重复挂起造成付款后像素蛋糕卡死。
- 管理员确认收款后会恢复目标窗口交互，并记录恢复结果。
- 付款后的同一次导出尾迹会被保护，避免图片实际导出时再次触发收费框。

### 4. 现场日志

- exe 运行日志仍写入 exe 同目录 `app.log`。
- 启动早期异常会尝试写入 `%TEMP%\SoftwareUsageMeter_bootstrap.log`，用于排查状态页空白或启动无日志问题。

## 当前版本状态

项目已完成核心功能开发，进入交付优化阶段。以下记录最近一次迭代的关键变更。

---

## 最新变更（本次迭代）

### 1. 放宽导出检测触发条件（核心改动）

**背景：** 雇主需在线下多台不同配置的电脑部署，原触发机制过于苛刻（视觉检测强制依赖 OCR 二次验证），导致部分机器无法正常弹出收费框。

**改动：**
- 视觉检测路径不再强制要求 OCR 验证，找到黄色导出按钮即可直接触发
- 导出按钮点击提升为独立强信号
- 居中对话框扫描默认开启，作为兜底检测手段
- OCR 仅负责识别导出张数，不再参与"是否弹窗"的决策

**效果：** 6 条检测路径（窗口标题 / 导出子进程 / 视觉按钮 / OCR 摘要 / 按钮点击 / 居中对话框扫描）任意一路命中即触发，显著提升多机兼容性。

**涉及文件：** `process_monitor.py`

### 2. 清理冗余文件

**删除内容：**
- 临时打包产物：`SoftwareUsageMeter.zip`、`package.bat`
- 诊断脚本：`diagnose_export.py`、`simple_diagnose.py`
- 测试脚本：`test_default_export.py`、`test_logic.py`、`test_ocr_debug.py`
- 测试目录：`tests/`（含编译缓存）
- 临时资源目录：`test_resources/`
- 误创建文件：`nul`
- Codex Plan 文件：`codex-plan-relax-export-detection.md`

**效果：** 项目结构精简，仅保留核心源码、配置与文档。

### 3. 文档全面更新

**更新文件：**
- `README.md` — 新增多路径检测说明，修复打包命令格式
- `开发说明.md` — 新增导出触发链路章节，更新项目结构、测试方法、排查建议
- `客户说明.md` — 简化 Q1 排查步骤，明确"即使 OCR 失败收费框仍会弹出"

---

## 当前项目结构

```
SoftwareUsageMeter/
├─ main.py              # 程序入口
├─ config_manager.py    # 配置管理
├─ process_monitor.py   # 进程监控 + 导出检测 + OCR
├─ timer_manager.py     # 计时管理
├─ payment_overlay.py   # 收费弹窗 UI
├─ admin_panel.py       # 管理后台
├─ tray_icon.py         # 系统托盘
├─ build.bat / build.spec # 打包脚本
├─ requirements.txt     # 依赖
├─ config.json          # 运行时配置
├─ app.log              # 运行日志
├─ resources/           # 资源文件
├─ dist/                # 打包输出
├─ README.md            # 项目概览
├─ 开发说明.md          # 开发者文档
├─ 客户说明.md          # 使用说明
└─ CHANGES_SUMMARY.md   # 本文件
```

---

## 已知限制与注意事项

1. **OCR 识别率**：Windows OCR 对部分分辨率/深色 UI 的识别效果不稳定，已通过 `default_export_count` 兜底
2. **调试截图**：如需排查 OCR 问题，可在 `config.json` 中开启 `debug_export_capture: true`
3. **管理员密码**：首次部署**必须**修改默认密码 `admin`

# SoftwareUsageMeter

门店自助修图设备计时计费工具。  
本程序用于监控“像素蛋糕”使用时长，在进入导出流程时弹出收费窗口，管理员确认收款后再恢复导出。

## 文档导航

| 文档 | 适用对象 | 内容 |
|------|----------|------|
| [客户说明.md](https://github.com/liguojing112/SoftwareUsageMeter/blob/main/%E5%AE%A2%E6%88%B7%E8%AF%B4%E6%98%8E.md) | 门店操作人员 | 日常使用流程、计费方式、后台设置、常见问题 |
| [开发说明.md]([C:\Workspace\PythonProjects\SoftwareUsageMeter\开发说明.md](https://github.com/liguojing112/SoftwareUsageMeter/blob/main/%E5%BC%80%E5%8F%91%E8%AF%B4%E6%98%8E.md)) | 开发者 / 运维 | 架构设计、模块职责、配置项、日志排障、打包说明 |

## 当前版本功能

- 自动监控 `PixCake.exe` 是否启动 / 退出
- 自动计时，按分钟计费
- 导出时弹出全屏置顶收费窗口
- 计费公式支持：
  - 使用时长费用
  - 导出张数费用
- 自动识别导出张数，识别失败时使用默认值兜底
- 支持普通导出页与“导出至本地”对话框
- 支持管理员密码确认收款
- 支持分别配置微信 / 支付宝收款码
- 支持管理页、密码页、状态页、收费页壁纸
- `app.log` 支持现场排障日志

## 计费公式

```text
总费用 = 使用时长（分钟）× 计时单价 + 导出张数 × 单张导出单价
```

## 快速开始

### 运行源码

```powershell
pip install -r requirements.txt
python main.py
```

### 打包

```powershell
build.bat
```

或：

```powershell
pyinstaller build.spec --clean --noconfirm
```

### 运行 exe

```text
dist\SoftwareUsageMeter.exe
```

## 首次配置

1. 启动程序
2. 右键托盘图标，打开管理设置
3. 输入管理员密码
4. 配置：
   - 计时单价
   - 单张导出单价
   - 微信收款码
   - 支付宝收款码
   - 壁纸
   - 目标进程名
5. 保存设置

默认管理员密码：`admin`

## 日志说明

程序运行后会在源码目录或 exe 同目录生成：

```text
app.log
```

日志里会记录：

- 运行环境
- 当前配置摘要
- 监控器初始化参数
- 目标程序启动 / 退出
- 导出检测诊断
- 收费窗口触发原因
- 导出结束 / 付款确认

如果现场再次出现“收费框没有弹出”，优先收集 `app.log`。

## 交付前建议测试

- 普通编辑页不弹收费框
- 普通导出页弹收费框
- “导出至本地”对话框弹收费框
- 管理员确认收款后可继续导出
- 退出程序后像素蛋糕仍可正常操作
- exe 同目录能生成 `app.log`

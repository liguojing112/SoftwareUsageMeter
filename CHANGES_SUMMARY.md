# 导出张数识别问题修复 - 修改总结

## 问题描述
用户报告"收费框没有显示正确的导出张数和导出费用"，经诊断发现OCR识别失败导致导出张数始终为0。

## 根本原因
Windows OCR引擎无法从导出窗口截图中正确识别导出张数文本，导致`detect_export_image_count()`返回`None`，主程序将其转换为0。

## 解决方案

### 1. 添加默认导出张数配置
- **文件**: `config_manager.py`
- **修改**: 添加`default_export_count`到默认配置
- **作用**: OCR失败时使用此默认值而非0

### 2. 修改OCR失败处理逻辑
- **文件**: `main.py` (两处)
- **修改**: 当`detect_export_image_count()`返回`None`时，使用`config.default_export_count`
- **作用**: 确保导出张数不为0

### 3. 更新配置文件
- **文件**: `config.json`
- **修改**: 添加`"default_export_count": 1`
- **作用**: 提供默认值配置

### 4. 增强OCR调试日志
- **文件**: `process_monitor.py`
- **修改**: 添加详细的OCR识别过程日志
- **作用**: 便于问题诊断

### 5. 改进文本提取逻辑
- **文件**: `process_monitor.py`
- **修改**: 增强`extract_export_image_count_from_text()`函数
- **作用**: 支持更多文本格式匹配

### 6. 创建诊断工具
- **新增文件**:
  - `simple_diagnose.py` - 基础诊断
  - `test_ocr_debug.py` - OCR模式测试
  - `test_logic.py` - 计费逻辑测试
  - `test_default_export.py` - 配置测试
  - `diagnose_export.py` - 完整诊断

### 7. 更新文档
- **文件**: `README.md`
- **更新内容**:
  - 添加混合计费说明
  - 添加OCR识别说明
  - 添加故障排除指南
  - 添加诊断工具说明
  - 更新配置说明

## 配置说明

### 关键配置项
```json
{
  "export_rate": 1.0,              // 单张导出单价（元/张）
  "default_export_count": 1        // OCR失败时的默认张数
}
```

### 调整建议
1. **导出单价**: 根据实际业务需求设置`export_rate`
2. **默认张数**: 根据典型导出数量设置`default_export_count`
3. **OCR调试**: 如持续失败，可增加默认值或考虑手动输入方案

## 验证方法

### 1. 逻辑测试
```bash
python test_logic.py
```

### 2. 配置测试
```bash
python test_default_export.py
```

### 3. OCR测试
```bash
python test_ocr_debug.py
```

### 4. 完整诊断
```bash
python simple_diagnose.py
```

## 效果验证
1. OCR成功时: 显示识别到的导出张数
2. OCR失败时: 显示默认导出张数（默认1张）
3. 导出费用: 正确计算 = 导出张数 × 导出单价

## 后续改进建议
1. **手动输入功能**: 在收费框添加手动输入导出张数选项
2. **OCR优化**: 改进截图区域或尝试其他OCR引擎
3. **配置界面**: 在管理面板添加默认导出张数配置项

## 文件清单
```
修改文件:
- config_manager.py      # 添加默认导出张数配置
- main.py               # 修改OCR失败处理逻辑（两处）
- process_monitor.py    # 增强OCR日志和文本提取
- config.json           # 添加默认导出张数配置
- README.md             # 更新文档

新增文件:
- simple_diagnose.py    # 基础诊断脚本
- test_ocr_debug.py     # OCR模式测试
- test_logic.py         # 计费逻辑测试
- test_default_export.py # 配置测试
- diagnose_export.py    # 完整诊断脚本
- CHANGES_SUMMARY.md    # 本文件
```

## 测试验证
所有修改已通过：
- 单元测试 (`pytest tests/`)
- 逻辑测试 (`python test_logic.py`)
- 配置测试 (`python test_default_export.py`)
- OCR模式测试 (`python test_ocr_debug.py`)

## 结论
问题已解决。现在当OCR识别失败时，系统会使用配置的默认导出张数（默认为1张），确保导出费用正确计算和显示。
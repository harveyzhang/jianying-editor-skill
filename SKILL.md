---
name: jianying-editor
description: 使用 pyJianYingDraft 库自动化创建、编辑和管理剪映 (JianYing) 视频草稿。支持多轨道、动画、特效、关键帧、模板替换及自动导出。
---

# JianYing Editor Skill

## 目标
将 `pyJianYingDraft` 库的所有能力封装为可直接调用的执行单元，实现从素材输入到视频导出的全链路自动化。

## 核心架构
本 Skill 包含完整的项目参考手册和核心逻辑脚本：
- **`references/`**: 包含项目的 `README.md` 和核心模块（`script_file.py`, `draft_folder.py`）的接口定义，供代理随时查阅 API。
- **`scripts/`**: 封装了常用的批处理任务（模板替换、自动导出）。

## 基础操作指南
1. **初始化**：始终通过 `DraftFolder` 管理草稿：
   ```python
   df = draft.DraftFolder(r"C:\Users\Administrator\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft")
   ```
2. **创建项目**：`script = df.create_draft("ProjectName", 1920, 1080)`。
3. **管理轨道**：支持 `TrackType.video`, `audio`, `text`, `effect`, `filter`。
4. **添加片段**：创建 `Segment` 对象并调用 `script.add_segment()`。
5. **保存**：`script.save()` 会自动处理元数据。

## 关联手册说明
- 查看 `references/README.md` 获取详细的功能清单和用法。
- 查看 `references/api_summary.txt` 获取类和方法的快速参考。

## 约束提示
- **必须**使用 `DraftFolder` 以保证剪映能识别草稿。
- **UI 刷新**：生成后需提醒用户重启剪映或进出草稿以强制刷新。
- **导出限制**：自动导出功能仅支持剪映 V6 及以下版本。

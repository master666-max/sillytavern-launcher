"""Localize bundled third-party extensions to Simplified Chinese.

Idempotent: re-running finds already-translated strings and does nothing.
Called by fetch_extensions.sh after the zips are refreshed, and safe to run
from update_st.sh chains. Only user-visible strings are covered; library
debug/error logs (mermaid/katex internals) are intentionally left alone.

Short/ambiguous words are matched only in quoted/HTML-tag form so they cannot
hit code identifiers; long phrases are replaced verbatim.
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXT_DIR = REPO / "assets-src" / "extensions"

# {dir: {relpath: {english: chinese}}}
TRANSLATIONS = {
    "Extension-Objective-main": {
        "manifest.json": {
            '"display_name": "Objective"': '"display_name": "目标"',
        },
        "index.js": {
            "Add Task": "添加任务",
            "Branch Task": "分支任务",
            "Complete Current Task": "完成当前任务",
            "Completion Check Prompt": "完成检查提示词",
            "Currently popped out": "目前已弹出",
            "Custom Prompt Select": "自定义提示词选择",
            "Delete Task": "删除任务",
            "Generation Prompt": "生成提示词",
            "Injected Prompt": "注入提示词",
            "Manual Task Check": "手动任务检查",
            "Move Down": "下移",
            "Move Up": "上移",
            "All tasks cleared": "所有任务已清空",
            "Are you sure you want to delete this prompt?": "确定要删除这个提示词吗？",
            "Cannot delete default prompt": "无法删除默认提示词",
            "Cannot save over default prompt": "无法覆盖保存默认提示词",
            "Checking for task completion.": "正在检查任务完成情况。",
            "Checks if the current task is completed": "检查当前任务是否已完成",
            "Custom Prompt name": "自定义提示词名称",
            "Delete Prompt": "删除提示词",
            "Done!": "完成！",
            "Failed to wait for group to finish generating": "等待群组生成完成失败",
            "Generating tasks for objective": "正在为目标生成任务",
            "Generating tasks for objective with prompt": "正在用提示词为目标生成任务",
            "Mark the current task as completed.": "将当前任务标记为已完成。",
            "New Prompt": "新建提示词",
            "No current task": "没有当前任务",
            "No current task to check": "没有可检查的当前任务",
            "Null task id": "任务 ID 为空",
            "Please set custom prompt name to save.": "请设置自定义提示词名称后再保存。",
            "Please wait...": "请稍候…",
            "Prompt saved as ": "提示词已保存为 ",
            "Trigger AI check of completed tasks": "触发 AI 检查已完成任务",
            "Update Prompt": "更新提示词",
        },
        "settings.html": {
            "Auto-Generate Frequency": "自动生成频率",
            "Go to parent task": "转到父任务",
            "Go to Parent": "转到父任务",
            "Hide Tasks": "隐藏任务",
            "Messages until next AI task completion check": "距下次 AI 完成检查的消息数",
            "Messages until next AI tasks regeneration": "距下次 AI 任务重新生成的消息数",
            ">Objective<": ">目标<",
            "Position in Chat": "聊天中的位置",
            "Task Check Frequency": "任务检查频率",
        },
    },
    "Extension-Live2d-main": {
        "window.html": {
            "Auto-send interaction": "自动发送交互",
            "Character:": "角色：",
            "Classified expressions mapping": "分类表情映射",
            "Click the refresh button to reload the model and model list": "点击刷新按钮重新加载模型和模型列表",
            "Debug Settings": "调试设置",
            "Default Animations": "默认动画",
            "Default click animation": "默认点击动画",
            "Enabled": "启用",
            "Follow cursor": "跟随光标",
            "Force animation loop (some model have no idle animation)": "强制动画循环（部分模型没有待机动画）",
            ">Gallery<": ">图库<",
            "Global Settings": "全局设置",
            "Hit areas mapping": "点击区域映射",
            "Live2d Model:": "Live2D 模型：",
            "Message to send when clicking the model. If empty, only play the animation.": "点击模型时发送的消息；留空则只播放动画。",
            "Model Animations": "模型动画",
            "Model Cursor Animations": "模型光标动画",
            "Model Mapping": "模型映射",
            "Model Settings": "模型设置",
            "Model Talk": "模型说话",
            "Model center X offset": "模型中心 X 偏移",
            "Model center Y offset": "模型中心 Y 偏移",
            "Model scale": "模型缩放",
            "Model-Eye Y offset": "模型眼睛 Y 偏移",
            "Mouth movement speed": "嘴部动作速度",
            "Mouth movement speed multiplier": "嘴部动作速度倍率",
            "Param Angle X": "参数 角度 X",
            "Param Angle Y": "参数 角度 Y",
            "Param Angle Z": "参数 角度 Z",
            "Param Body Angle X": "参数 身体角度 X",
            "Param Breath": "参数 呼吸",
            "Param Eye Ball X": "参数 眼球 X",
            "Param Eye Ball Y": "参数 眼球 Y",
            "Param mouth open Y id": "嘴部开合 Y 参数 ID",
            "Play when starting a chat with the character": "与角色开始聊天时播放",
            "Played when classified expression has no mapping set": "分类表情未设置映射时播放",
            "Reload all live2d models (debug)": "重新加载全部 Live2D 模型（调试）",
            ">Remove<": ">移除<",
            "Reset model before animation (allow to spam click)": "动画前重置模型（允许连点）",
            "Scale of the live2d model": "Live2D 模型的缩放",
            "Set the model X position (alternative to dragging)": "设置模型 X 坐标（也可直接拖拽）",
            "Set the model Y position (alternative to dragging)": "设置模型 Y 坐标（也可直接拖拽）",
            "Show model frames (usefull from dragging)": "显示模型边框（便于拖拽）",
            "Starter animation": "入场动画",
            "Time per character": "每个字符的时长",
        },
        "gallery/galleryDlg.html": {
            "A replica of the Gallery by Pyrater and Nitral": "图库（复刻自 Pyrater 与 Nitral）",
            "Gallery of Life2D Models": "Live2D 模型图库",
            "Search for path or model name": "搜索路径或模型名",
            "Search for tags (separted by ',')": "搜索标签（用逗号分隔）",
            "Show All": "显示全部",
            "breast size": "胸围",
            "eye color": "眼睛颜色",
            "hair color": "发色",
            "hair length": "发长",
            "sex": "性别",
        },
        "ui.js": {
            "Select Character": "选择角色",
            "Select parameter id": "选择参数 ID",
            "Write message te send when clicking the area.": "点击该区域时发送的消息。",
            '"None"': '"无"',
        },
        "utils.js": {
            "Select expression": "选择表情",
            "Select motion": "选择动作",
            "Select parameter id": "选择参数 ID",
        },
    },
    "Extension-Dice-main": {
        "manifest.json": {
            '"display_name": "D&D Dice"': '"display_name": "D&D 骰子"',
        },
        "button.html": {
            "Roll Dice": "掷骰子",
        },
        "index.js": {
            "Dice Roll": "掷骰",
            "Do not display the result in chat": "不在聊天中显示结果",
            "Enter the dice formula:<br><i>(for example, <tt>2d6</tt>)</i>": "输入骰子公式：<br><i>（例如 <tt>2d6</tt>）</i>",
            "Invalid dice formula": "骰子公式无效",
            "Roll the dice.": "掷骰子。",
            "The name of the persona rolling the dice": "掷骰的角色名",
        },
        "settings.html": {
            ">D&D Dice<": ">D&D 骰子<",
            "Use function tool": "使用函数调用",
        },
    },
    "Extension-MessageLimit-main": {
        "manifest.json": {
            '"display_name": "Message Limit"': '"display_name": "消息数量限制"',
        },
        "index.js": {
            "Desired state of the message limit.": "消息数量限制的开关状态。",
            "Desired state of the message limit for background prompts.": "后台提示词的消息数量限制开关状态。",
            "Limit must be a finite number.": "限制必须是一个有限数字。",
        },
    },
    "Extension-WebSearch-main": {
        "index.js": {
            ">Web Search<": ">网页搜索<",
            "Web search results for ": "网页搜索结果：",
            "Are you sure?": "确定吗？",
            "Clear the WebSearch cache": "清空网页搜索缓存",
            "Enter a test message": "输入测试消息",
            "How to make a sandwich": "如何制作三明治",
            "Include full parsed pages": "包含完整解析的页面",
            "Include page snippets": "包含页面摘要",
            "No arguments provided": "未提供参数",
            "No links provided": "未提供链接",
            "No query provided": "未提供查询",
            "No search query specified": "未指定搜索查询",
            "No search result type specified": "未指定搜索结果类型",
            "Perform a web search and download the results.": "执行网页搜索并下载结果。",
            "Performs a test search using the current settings.": "使用当前设置执行一次测试搜索。",
            "Remove Key": "移除密钥",
            "Removes all search results stored in the local cache.": "移除本地缓存中的全部搜索结果。",
            "Search is not available": "搜索不可用",
            "Test the WebSearch extension": "测试网页搜索扩展",
            "Visit Links": "访问链接",
            "Visit the web links and get the content of the relevant pages.": "访问网页链接并获取相关页面内容。",
            "Visiting the web links": "正在访问网页链接",
            "Web Query used in search engine.": "搜索引擎中使用的查询词。",
            "Web links to visit.": "要访问的网页链接。",
            "Data Bank module is not available": "数据银行模块不可用",
        },
    },
}


def localize(ext_dir: Path, relpath: str, mapping: dict) -> tuple:
    target = ext_dir / relpath
    if not target.is_file():
        return 0, 0
    text = target.read_text(encoding="utf-8")
    hits = 0
    for en, zh in mapping.items():
        if en in text:
            text = text.replace(en, zh)
            hits += 1
    if hits:
        target.write_text(text, encoding="utf-8")
    return hits, len(mapping)


def main():
    if not EXT_DIR.is_dir():
        print(f"skip: {EXT_DIR} not found")
        return 0
    total = 0
    for ext, files in TRANSLATIONS.items():
        ext_dir = EXT_DIR / ext
        if not ext_dir.is_dir():
            print(f"skip: {ext} (not present)")
            continue
        for relpath, mapping in files.items():
            hits, size = localize(ext_dir, relpath, mapping)
            total += hits
            print(f"{ext}/{relpath}: {hits}/{size} entries translated")
    print(f"localization done, {total} entries replaced this run")
    return 0


if __name__ == "__main__":
    sys.exit(main())

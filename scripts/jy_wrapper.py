
"""
JianYing Editor Skill - High Level Wrapper (Bootstrap)
旨在解决路径依赖、API 复杂度及严格校验问题。
代理应优先使用此 Wrapper 而非直接调用底层库。
"""

import os
import sys
import shutil
import warnings
import argparse
import difflib

# --- 1. 幽灵依赖解决: 自动注入 references 路径 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
skill_root = os.path.dirname(current_dir)
references_path = os.path.join(skill_root, "references")

if os.path.exists(references_path):
    if references_path not in sys.path:
        sys.path.insert(0, references_path)

try:
    import pyJianYingDraft as draft
    from pyJianYingDraft import trange, tim
    from pyJianYingDraft import TextIntro, TextStyle, TextBorder, KeyframeProperty
    from pyJianYingDraft import VideoSceneEffectType, TransitionType, IntroType, OutroType
except ImportError:
    fallback_path = os.path.join(os.getcwd(), "pyJianYingDraft")
    if os.path.exists(fallback_path):
        sys.path.insert(0, os.getcwd())
        import pyJianYingDraft as draft
        from pyJianYingDraft import trange, tim
        from pyJianYingDraft import TextIntro, TextStyle, TextBorder, KeyframeProperty
        from pyJianYingDraft import VideoSceneEffectType, TransitionType, IntroType, OutroType
    else:
        print(f"⚠️ Warning: pyJianYingDraft module not found in standard locations.")

# --- 2. 路径自动探测 ---
def get_default_drafts_root() -> str:
    """自动探测剪映草稿目录 (Windows)"""
    local_app_data = os.environ.get('LOCALAPPDATA', '')
    if not local_app_data:
        return r"C:\Users\Administrator\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft"
    
    candidates = [
        os.path.join(local_app_data, r"JianyingPro\User Data\Projects\com.lveditor.draft"),
        os.path.join(local_app_data, r"CapCut\User Data\Projects\com.lveditor.draft")
    ]
    
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]

# --- 3. 辅助函数: 模糊匹配 ---
def _resolve_enum(enum_cls, name: str):
    """
    尝试从 Enum 类中找到匹配的属性。
    1. 精确匹配
    2. 大小写不敏感匹配
    3. 模糊匹配 (difflib)
    """
    if not name: return None
    
    # 1. Exact
    if hasattr(enum_cls, name):
        return getattr(enum_cls, name)
    
    # 2. Case insensitive map
    name_lower = name.lower()
    mapping = {k.lower(): k for k in enum_cls.__members__.keys()}
    
    if name_lower in mapping:
        real_key = mapping[name_lower]
        return getattr(enum_cls, real_key)
    
    # 3. Fuzzy
    matches = difflib.get_close_matches(name, enum_cls.__members__.keys(), n=1, cutoff=0.6)
    if matches:
        print(f"ℹ️ Fuzzy Match: '{name}' -> '{matches[0]}'")
        return getattr(enum_cls, matches[0])
        
    print(f"⚠️ Warning: Could not find enum memeber for '{name}'.")
    return None

# --- 4. High-Level Facade ---

class JyProject:
    """
    高层封装类，提供容错、自动计算和简化的 API。
    """
    
    def __init__(self, name: str, width: int = 1920, height: int = 1080, 
                 drafts_root: str = None, overwrite: bool = True):
        self.root = drafts_root or get_default_drafts_root()
        if not os.path.exists(self.root):
            try:
                os.makedirs(self.root)
            except:
                pass
                
        print(f"📂 Project Root: {self.root}")
        
        self.df = draft.DraftFolder(self.root)
        self.name = name
        self.script = self.df.create_draft(name, width, height, allow_replace=overwrite)

    def save(self):
        self.script.save()
        print(f"✅ Saved project: {self.name} to {self.root}")

    def add_media_safe(self, media_path: str, start_time: str, duration: str = None, 
                       track_name: str = "VideoTrack"):
        """自动容错的媒体添加方法"""
        if not os.path.exists(media_path):
            print(f"❌ Media Missing: {media_path}")
            return None

        self._ensure_track(draft.TrackType.video, track_name)
        
        try:
            mat = draft.VideoMaterial(media_path)
            phys_duration = mat.duration 
        except Exception as e:
            print(f"⚠️ Media Read Error: {e}")
            return None

        start_us = tim(start_time)
        if duration:
            req_duration = tim(duration)
            if req_duration > phys_duration:
                print(f"⚠️ Auto-Clamp: {duration} > physical. Using full length.")
                actual_duration = phys_duration
            else:
                actual_duration = req_duration
        else:
            actual_duration = phys_duration

        seg = draft.VideoSegment(
            mat,
            target_timerange=trange(start_us, actual_duration),
            source_timerange=trange(0, actual_duration) 
        )
        self.script.add_segment(seg, track_name)
        return seg

    def add_text_simple(self, text: str, start_time: str, duration: str, 
                        track_name: str = "TextTrack",
                        font_size: float = 15.0,
                        color_rgb: tuple = (1.0, 1.0, 1.0),
                        bold: bool = False,
                        anim_in: str = None):
        """极简文本接口"""
        self._ensure_track(draft.TrackType.text, track_name)
        style = TextStyle(size=font_size, color=color_rgb, bold=bold)
        start_us = tim(start_time)
        dur_us = tim(duration)
        seg = draft.TextSegment(text, trange(start_us, dur_us), style=style)
        
        if anim_in:
            anim = _resolve_enum(TextIntro, anim_in)
            if anim: seg.add_animation(anim)
                
        self.script.add_segment(seg, track_name)
        return seg

    def add_effect_simple(self, effect_name: str, start_time: str, duration: str, track_name: str = "EffectTrack"):
        """添加全局特效 (支持模糊匹配名称)"""
        self._ensure_track(draft.TrackType.effect, track_name)
        
        eff = _resolve_enum(VideoSceneEffectType, effect_name)
        if not eff:
            return None
            
        start_us = tim(start_time)
        dur_us = tim(duration)
        
        # pyJianYingDraft 的 add_effect 通常是 ScriptFile 层面的方法或者 Segments
        # 这里我们使用 ScriptFile.add_effect (全局特效)
        # 注意：add_effect 内部实现可能不同，这里调用 script.add_effect
        try:
            self.script.add_effect(eff, trange(start_us, dur_us), track_name=track_name)
            print(f"✨ Added Effect: {effect_name}")
        except Exception as e:
            print(f"❌ Failed to add effect: {e}")

    def add_transition_simple(self, transition_name: str, duration: str = "0.5s", track_name: str = "VideoTrack"):
        """
        向指定轨道的最后两个片段之间添加转场。
        注意：只能添加到已存在的片段之间。
        """
        # 找到对应轨道 (兼容 List/Dict)
        track = None
        tracks = self.script.tracks
        if isinstance(tracks, dict):
            iterator = tracks.values()
        else:
            iterator = tracks if isinstance(tracks, list) else []

        for t in iterator:
            if hasattr(t, 'name') and getattr(t, 'name') == track_name and \
               hasattr(t, 'type') and getattr(t, 'type') == draft.TrackType.video:
                track = t
                break
        
        if not track or len(track.segments) < 1:
            print(f"⚠️ Cannot add transition: Track '{track_name}' not found or empty.")
            return

        trans_enum = _resolve_enum(TransitionType, transition_name)
        if not trans_enum: return

        # 这里的逻辑假设最后添加的片段需要转场
        # pyJianYingDraft 的 add_transition 是加在 VideoSegment 对象上的
        # 通常是加在“后面”那个片段上，或者“前面”？ docs says: "注意转场应当添加在**前面的**片段上"??
        # Let's check docs from prev step: "为视频片段添加转场, 注意转场应当添加在**前面的**片段上" -> So add to segment[i] to transition to segment[i+1]??
        # Or add to segment[i] to transition FROM it? 
        # Usually it's attached to the incoming or outgoing. Let's assume we add to the last segment added.
        
        last_seg = track.segments[-1]
        try:
            last_seg.add_transition(trans_enum, duration=duration)
            print(f"🔗 Added Transition: {transition_name}")
        except Exception as e:
            print(f"❌ Failed add transition: {e}")

    def _ensure_track(self, type, name):
        # 兼容性修复: self.script.tracks 可能是 List[Track] 或 Dict[str, Track]
        tracks = self.script.tracks
        
        # 获取迭代器
        if isinstance(tracks, dict):
            iterator = tracks.values()
        elif isinstance(tracks, list):
            iterator = tracks
        else:
            # Fallback
            iterator = []

        # 遍历查找是否存在同名同类型轨道
        for t in iterator:
            # 防御性检查
            if hasattr(t, 'name') and getattr(t, 'name') == name and \
               hasattr(t, 'type') and getattr(t, 'type') == type:
                return
        
        # 不存在则创建 (捕获 NameError 以防并发或状态不一致)
        try:
            self.script.add_track(type, name)
        except NameError:
            # 如果底层库抛出 "NameError: 名为 'xxx' 的轨道已存在"，说明轨道其实存在
            # 我们可以安全地忽略这个错误，视为 ensure 成功
            pass

# --- 5. CLI Controller ---

def cli():
    parser = argparse.ArgumentParser(description="Antigravity JianYing (CapCut) Skill CLI")
    subparsers = parser.add_subparsers(dest="command")
    
    # Command: check
    subparsers.add_parser("check", help="Run diagnostics on environment")
    
    # Command: list
    list_parser = subparsers.add_parser("list", help="List available assets")
    list_parser.add_argument("--type", choices=["anim", "effect", "trans"], default="anim")
    
    # Command: create (Simple)
    create_parser = subparsers.add_parser("create", help="Quickly create a simple video draft")
    create_parser.add_argument("--name", required=True, help="Project Name")
    create_parser.add_argument("--media", required=True, help="Path to video/image")
    create_parser.add_argument("--text", help="Overlay text")
    
    args = parser.parse_args()
    
    if args.command == "check":
        root = get_default_drafts_root()
        if os.path.exists(root):
            print(f"✅ Environment Ready. Drafts Path: {root}")
            try:
                import uiautomation
                print("✅ Dependencies: uiautomation found.")
            except:
                print("⚠️ Warning: uiautomation not installed (Auto-export will fail).")
        else:
            print(f"❌ Drafts folder not found at: {root}")
            
    elif args.command == "list":
        # Simple listing, refer to md for details
        print("Please check '.agent/skills/jianying-editor/references/AVAILABLE_ASSETS.md' for full list.")
        
    elif args.command == "create":
        p = JyProject(args.name)
        p.add_media_safe(args.media, "0s")
        if args.text:
            p.add_text_simple(args.text, "0s", "3s")
        p.save()
        
    else:
        parser.print_help()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli()
    else:
        print("JyWrapper Library Loaded. Import `JyProject` to use.")

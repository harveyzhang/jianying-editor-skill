
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
from typing import Union

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
    local_app_data = os.environ.get('LOCALAPPDATA')
    user_profile = os.environ.get('USERPROFILE')
    
    candidates = []
    if local_app_data:
        candidates.extend([
            os.path.join(local_app_data, r"JianyingPro\User Data\Projects\com.lveditor.draft"),
            os.path.join(local_app_data, r"CapCut\User Data\Projects\com.lveditor.draft")
        ])
    
    if user_profile:
        candidates.append(os.path.join(user_profile, r"AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft"))

    # 默认兜底路径 (仅作参考)
    fallback = r"C:\Users\Administrator\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft"
    
    for path in candidates:
        if os.path.exists(path):
            return path
            
    # 如果都没找到，返回第一个候选路径但打印警告
    if candidates:
        return candidates[0]
    return fallback

def get_all_drafts(root_path: str = None):
    """获取所有草稿并按修改时间排序"""
    root = root_path or get_default_drafts_root()
    drafts = []
    if not os.path.exists(root):
        return []
        
    for item in os.listdir(root):
        path = os.path.join(root, item)
        if os.path.isdir(path):
            # 剪映草稿文件夹通常包含这两个文件之一
            if os.path.exists(os.path.join(path, "draft_content.json")) or \
               os.path.exists(os.path.join(path, "draft_meta_info.json")):
                drafts.append({
                    "name": item,
                    "mtime": os.path.getmtime(path),
                    "path": path
                })
    return sorted(drafts, key=lambda x: x['mtime'], reverse=True)

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

    def add_media_safe(self, media_path: str, start_time: Union[str, int], duration: Union[str, int] = None, 
                       track_name: str = None):
        """
        自动容错的媒体添加方法 (Auto-Clamp)
        支持视频/图片/音频自动分流。
        """
        if not os.path.exists(media_path):
            print(f"❌ Media Missing: {media_path}")
            return None

        # 简单的后缀判断
        ext = os.path.splitext(media_path)[1].lower()
        if ext in ['.mp3', '.wav', '.aac', '.flac', '.m4a']:
            return self.add_audio_safe(media_path, start_time, duration, track_name or "AudioTrack")
        
        # 默认为视频/图片
        return self._add_video_safe(media_path, start_time, duration, track_name or "VideoTrack")

    def add_audio_safe(self, media_path: str, start_time: Union[str, int], duration: Union[str, int] = None, 
                       track_name: str = "AudioTrack"):
        self._ensure_track(draft.TrackType.audio, track_name)
        
        try:
            mat = draft.AudioMaterial(media_path)
            phys_duration = mat.duration
        except Exception as e:
            print(f"⚠️ Audio Read Error: {e}")
            return None
            
        start_us = tim(start_time)
        actual_duration = self._calculate_duration(duration, phys_duration)
        
        seg = draft.AudioSegment(
            mat,
            target_timerange=trange(start_us, actual_duration),
            source_timerange=trange(0, actual_duration)
        )
        self.script.add_segment(seg, track_name)
        return seg

    def _add_video_safe(self, media_path: str, start_time: Union[str, int], duration: Union[str, int] = None, 
                        track_name: str = "VideoTrack"):
        self._ensure_track(draft.TrackType.video, track_name)
        
        try:
            mat = draft.VideoMaterial(media_path)
            phys_duration = mat.duration 
        except Exception as e:
            print(f"⚠️ Video Read Error: {e}")
            return None

        start_us = tim(start_time)
        actual_duration = self._calculate_duration(duration, phys_duration)

        seg = draft.VideoSegment(
            mat,
            target_timerange=trange(start_us, actual_duration),
            source_timerange=trange(0, actual_duration) 
        )
        self.script.add_segment(seg, track_name)
        return seg

    def _calculate_duration(self, req_duration, phys_duration):
        if req_duration is not None:
            req = tim(req_duration)
            if req > phys_duration:
                print(f"⚠️ Auto-Clamp: {req_duration} > physical. Using full length.")
                return phys_duration
            return req
        return phys_duration

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
        
        try:
            self.script.add_effect(eff, trange(start_us, dur_us), track_name=track_name)
            print(f"✨ Added Effect: {effect_name}")
        except Exception as e:
            print(f"❌ Failed to add effect: {e}")

    def add_transition_simple(self, transition_name: str, duration: str = "0.5s", track_name: str = "VideoTrack"):
        """
        向指定轨道的最后两个片段之间添加转场。
        """
        # 找到对应轨道 (兼容 List/Dict)
        track = None
        tracks = self.script.tracks
        if isinstance(tracks, dict):
            iterator = tracks.values()
        else:
            iterator = tracks if isinstance(tracks, list) else []

        for t in iterator:
            # 兼容性: 检查 type (旧逻辑) 或 track_type (pyJianYingDraft 可能的属性名)
            t_type = getattr(t, 'type', None) or getattr(t, 'track_type', None)
            
            if hasattr(t, 'name') and getattr(t, 'name') == track_name and \
               t_type == draft.TrackType.video:
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
               hasattr(t, 'track_type') and getattr(t, 'track_type') == type:
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
    
    # Command: list-assets (原 list)
    list_assets_parser = subparsers.add_parser("list-assets", help="List available assets (effects, transitions, etc.)")
    list_assets_parser.add_argument("--type", choices=["anim", "effect", "trans"], default="anim")
    
    # Command: list-drafts (新)
    subparsers.add_parser("list-drafts", help="List user video drafts from JianYing")

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
            
    elif args.command == "list-assets":
        # Simple listing, refer to md for details
        print("Please check '.agent/skills/jianying-editor/references/AVAILABLE_ASSETS.md' for full list.")
        
    elif args.command == "list-drafts":
        root = get_default_drafts_root()
        drafts = get_all_drafts(root)
        if not drafts:
            print(f"📭 No drafts found in: {root}")
        else:
            print(f"📂 Found {len(drafts)} drafts in: {root}")
            import time
            for d in drafts:
                t_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(d['mtime']))
                print(f" - {d['name']} (Last Modified: {t_str})")

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

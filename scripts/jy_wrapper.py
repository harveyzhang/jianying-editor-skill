
"""
JianYing Editor Skill - High Level Wrapper (Bootstrap)
旨在解决路径依赖、API 复杂度及严格校验问题。
代理应优先使用此 Wrapper 而非直接调用底层库。
"""

import os
import sys
import shutil
import warnings

# --- 1. 幽灵依赖解决: 自动注入 references 路径 ---
# 逻辑：脚本位于 .agent/skills/jianying-editor/scripts/jy_wrapper.py
# 目标 references: .agent/skills/jianying-editor/references
current_dir = os.path.dirname(os.path.abspath(__file__))
skill_root = os.path.dirname(current_dir)
references_path = os.path.join(skill_root, "references")

# 如果 references 存在，优先使用其中的库
if os.path.exists(references_path):
    # 将 references/pyJianYingDraft 的上级目录加入 path
    # 实际上 references 目录下直接就是 pyJianYingDraft 文件夹
    if references_path not in sys.path:
        sys.path.insert(0, references_path)

try:
    import pyJianYingDraft as draft
    from pyJianYingDraft import trange, tim
    from pyJianYingDraft import TextIntro, TextStyle, TextBorder, KeyframeProperty
except ImportError:
    # 尝试回退查找 (兼容用户可能手动修改了目录结构的情况)
    fallback_path = os.path.join(os.getcwd(), "pyJianYingDraft")
    if os.path.exists(fallback_path):
        sys.path.insert(0, os.getcwd())
        import pyJianYingDraft as draft
        from pyJianYingDraft import trange, tim
    else:
        # 如果还是找不到，但不 crash，允许调用者处理
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
            
    # Default fallback
    return candidates[0]

# --- 3. High-Level Facade ---

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
        
        # 自动覆盖逻辑
        draft_path = os.path.join(self.root, name)
        if os.path.exists(draft_path) and overwrite:
            # 实际上 create_draft(allow_replace=True) 会处理，这里仅做提示
            pass 
        
        self.script = self.df.create_draft(name, width, height, allow_replace=overwrite)

    def save(self):
        self.script.save()
        print(f"✅ Saved project: {self.name}")

    def add_media_safe(self, media_path: str, start_time: str, duration: str = None, 
                       track_name: str = "VideoTrack"):
        """自动容错的媒体添加方法 (Auto-Clamp)"""
        if not os.path.exists(media_path):
            print(f"❌ Media Missing: {media_path}")
            return None

        # 确保轨道
        self._ensure_track(draft.TrackType.video, track_name)
        
        # 1. 探测素材时长
        # 注意: VideoMaterial 初始化会读取文件头，需确保文件是有效视频/图片
        try:
            mat = draft.VideoMaterial(media_path)
            phys_duration = mat.duration 
        except Exception as e:
            print(f"⚠️ Media Read Error: {e}")
            return None

        # 2. 自动截断 (Auto-Clamp)
        start_us = tim(start_time)
        if duration:
            req_duration = tim(duration)
            if req_duration > phys_duration:
                print(f"⚠️ Auto-Clamp: {duration} > physical {phys_duration/1000000:.2f}s. Using full length.")
                actual_duration = phys_duration
            else:
                actual_duration = req_duration
        else:
            actual_duration = phys_duration

        # 3. 创建片段
        # target_timerange 决定了在轨道上的位置: [start_time, start_time + duration]
        # source_timerange 决定了截取素材哪一段: [0, duration] (这里暂不支持从素材中间截取，简化 API)
        
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
        
        # 字符串转动画枚举
        if anim_in:
            if hasattr(TextIntro, anim_in):
                seg.add_animation(getattr(TextIntro, anim_in))
            else:
                print(f"⚠️ Animation '{anim_in}' unknown. Ignoring.")
                
        self.script.add_segment(seg, track_name)
        return seg

    def _ensure_track(self, type, name):
        # 检查轨道是否存在，简化逻辑：不重复创建同名轨道
        for t in self.script.tracks:
            if t.name == name and t.type == type:
                return
        self.script.add_track(type, name)

if __name__ == "__main__":
    print("JyWrapper loaded. Use 'from jy_wrapper import JyProject' to start.")

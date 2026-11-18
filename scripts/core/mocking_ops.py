import os
import sys
import json
import uuid
import pyJianYingDraft as draft

class MockVideoMaterial(draft.VideoMaterial):
    def __init__(self, material_id, duration, name, path):
        self.material_id = material_id
        self.duration = duration
        self.material_name = name
        self.path = path
    def serialize(self):
        return {
            "id": self.material_id, "type": "video", "name": self.material_name, "path": self.path,
            "duration": self.duration, "material_id": self.material_id
        }

class MockAudioMaterial(draft.AudioMaterial):
    def __init__(self, material_id, duration, name, path):
        self.material_id = material_id
        self.duration = duration
        self.material_name = name
        self.path = path
    def serialize(self):
        return {
            "id": self.material_id, "type": "audio", "name": self.material_name, "path": self.path,
            "duration": self.duration, "material_id": self.material_id
        }

class CompoundSegment:
    def __init__(self, material_id, target_timerange):
        self.material_id = material_id
        self.target_timerange = target_timerange
    def serialize(self):
        return {
             "id": str(uuid.uuid4()).upper(), "material_id": self.material_id,
             "target_timerange": self.target_timerange.serialize(),
             "render_index": 0, "type": "video"
        }

class MockingOpsMixin:
    """
    JyProject 的协议补丁与伪物料 Mixin。
    """
    def _force_activate_adjustments(self):
        content_path = os.path.join(self.root, self.name, "draft_info.json")
        if not os.path.exists(content_path):
            content_path = os.path.join(self.root, self.name, "draft_content.json")
        if not os.path.exists(content_path): return

        try:
            with open(content_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            has_modified = False
            materials = data.setdefault("materials", {})
            all_effects = materials.setdefault("effects", [])

            PROP_MAP = {"KFTypeBrightness": "brightness", "KFTypeContrast": "contrast", "KFTypeSaturation": "saturation"}
            jy_res_path = "C:/Program Files/JianyingPro/5.9.0.11632/Resources/DefaultAdjustBundle/combine_adjust"

            for track in data.get("tracks", []):
                for seg in track.get("segments", []):
                    kfs = seg.get("common_keyframes", [])
                    active_props = [kf.get("property_type") for kf in kfs if kf.get("property_type") in PROP_MAP]

                    if active_props:
                        seg["enable_adjust"] = True
                        seg["enable_color_correct_adjust"] = True
                        refs = seg.setdefault("extra_material_refs", [])

                        for prop in active_props:
                            mat_type = PROP_MAP[prop]
                            if not any(m.get("type") == mat_type and m["id"] in refs for m in all_effects):
                                new_id = str(uuid.uuid4()).upper()
                                shadow_mat = {
                                    "type": mat_type, "value": 0.0, "path": jy_res_path, "id": new_id,
                                    "apply_target_type": 0, "platform": "all", "source_platform": 0, "version": "v2"
                                }
                                all_effects.append(shadow_mat)
                                refs.append(new_id)
                                has_modified = True

            if has_modified:
                with open(content_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Force activation failed: {e}")

    def _patch_cloud_material_ids(self):
        if not self._cloud_audio_patches and not self._cloud_text_patches: return
        content_path = os.path.join(self.root, self.name, "draft_info.json")
        if not os.path.exists(content_path):
            content_path = os.path.join(self.root, self.name, "draft_content.json")
        if not os.path.exists(content_path): return

        try:
            with open(content_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            has_modified = False
            materials = data.get("materials", {})
            audios = materials.get("audios", [])
            for mat in audios:
                path = mat.get("path", "")
                for dummy_path, patch_info in self._cloud_audio_patches.items():
                    if dummy_path in path:
                        if patch_info["type"] == "music":
                            mat["music_id"] = patch_info["id"]
                            mat["type"] = "music"
                            has_modified = True
            
            if has_modified:
                with open(content_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def _patch_capcut_metadata(self):
        """
        跨平台兼容：当探测到运行于 CapCut 环境（或 macOS 安装 CapCut）时，
        补齐 CapCut 桌面版所需的签名（app_source='cc', app_id=359289, new_version='189.0.0'）
        以及 draft_meta_info / root_meta_info 的时长、素材体积和封面，以防出现 0.0B | 00:00 无法打开的问题。
        """
        is_capcut = "CapCut" in getattr(self, "root", "") or (
            sys.platform == "darwin" and os.path.exists("/Applications/CapCut.app")
        )
        if not is_capcut:
            return

        draft_path = os.path.join(self.root, self.name)
        if not os.path.exists(draft_path):
            return

        import glob
        info_targets = [os.path.join(draft_path, "draft_info.json")]
        for p in glob.glob(os.path.join(draft_path, "Timelines", "*", "draft_info.json")):
            info_targets.append(p)

        duration_us = self.get_track_duration("VideoTrack")

        for ip in info_targets:
            if not os.path.exists(ip):
                continue
            try:
                with open(ip, "r", encoding="utf-8") as f:
                    d = json.load(f)
                d_modified = False

                plat = d.setdefault("platform", {})
                if plat.get("app_source") != "cc":
                    plat["app_source"] = "cc"
                    plat["app_id"] = 359289
                    plat["app_version"] = "9.6.0"
                    d_modified = True

                last_plat = d.setdefault("last_modified_platform", {})
                if last_plat.get("app_source") != "cc":
                    last_plat["app_source"] = "cc"
                    last_plat["app_id"] = 359289
                    last_plat["app_version"] = "9.6.0"
                    d_modified = True

                if d.get("new_version") != "189.0.0":
                    d["new_version"] = "189.0.0"
                    d_modified = True

                if not duration_us:
                    duration_us = d.get("duration", 0)

                if d_modified:
                    with open(ip, "w", encoding="utf-8") as f:
                        json.dump(d, f, ensure_ascii=False)
            except Exception as e:
                print(f"[warn] Failed to patch CapCut info {ip}: {e}")

        # 计算 materials 文件夹大小
        mat_dir = os.path.join(draft_path, "materials")
        mat_size = 0
        first_video_path = None
        if os.path.exists(mat_dir):
            for fname in os.listdir(mat_dir):
                fpath = os.path.join(mat_dir, fname)
                if os.path.isfile(fpath):
                    mat_size += os.path.getsize(fpath)
                    if not first_video_path and fname.lower().endswith((".mp4", ".mov", ".m4v", ".webm")):
                        first_video_path = fpath

        # 确保 draft_cover.jpg 存在
        cover_path = os.path.join(draft_path, "draft_cover.jpg")
        if not os.path.exists(cover_path) and first_video_path:
            try:
                import subprocess
                subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "1", "-i", first_video_path,
                     "-vf", "scale=640:360", "-frames:v", "1", "-q:v", "2", cover_path],
                    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except Exception:
                pass

        # 补齐 draft_meta_info.json
        meta_file = os.path.join(draft_path, "draft_meta_info.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta["tm_duration"] = duration_us
                meta["draft_timeline_materials_size_"] = mat_size
                if os.path.exists(cover_path):
                    meta["draft_cover"] = "draft_cover.jpg"
                with open(meta_file, "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False)
            except Exception as e:
                print(f"[warn] Failed to patch draft_meta_info: {e}")

        # 补齐 root_meta_info.json
        root_meta_file = os.path.join(self.root, "root_meta_info.json")
        if os.path.exists(root_meta_file):
            try:
                with open(root_meta_file, "r", encoding="utf-8") as f:
                    root_meta = json.load(f)
                has_root_mod = False
                for item in root_meta.get("all_draft_store", []):
                    if item.get("draft_name") == self.name or item.get("draft_fold_path") == draft_path:
                        item["tm_duration"] = duration_us
                        item["draft_timeline_materials_size"] = mat_size
                        if os.path.exists(cover_path):
                            item["draft_cover"] = cover_path
                        has_root_mod = True
                if has_root_mod:
                    with open(root_meta_file, "w", encoding="utf-8") as f:
                        json.dump(root_meta, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[warn] Failed to patch root_meta_info: {e}")

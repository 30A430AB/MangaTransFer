import sys
import pooch
from pathlib import Path

# 项目根目录
_PROJECT_ROOT = Path(__file__).parent.parent

# 支持的图片扩展名
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.avif'}

class DirPaths:
    TEMP = "temp"
    TEXT = "temp/text"
    RAW_MASK = "temp/raw_mask"
    TEXT_MASK = "temp/text_mask"
    THUMBS = "temp/thumbs"
    NEW_MASK = "mask"
    INPAINTED = "inpainted"
    RESULT = "result"

class DataPaths:
    DATA_ROOT = _PROJECT_ROOT / "data"
    MODELS_DIR = DATA_ROOT / "models"
    LIBS_DIR = DATA_ROOT / "libs"

    COMIC_TEXT_DETECTOR = MODELS_DIR / "comictextdetector.pt"
    RESNET18 = MODELS_DIR / "resnet18-f37072fd.pth"
    LAMA = MODELS_DIR / "anime-manga-big-lama.pt"

    PATCHMATCH_SO = LIBS_DIR / "libpatchmatch.so"
    OPENCV_DLL = LIBS_DIR / "opencv_world455.dll"
    PATCHMATCH_INPAINT_DLL = LIBS_DIR / "patchmatch_inpaint.dll"

class InpaintAlgorithm:
    PATCHMATCH = "PatchMatch"
    LAMA = "LaMa"

class ResourceManager:
    BASE_URL = "https://github.com/30A430AB/MangaTransFer/releases/download/v0.1.0/"
    
    # 本地相对路径 (相对于 data/) -> (远程文件名, MD5)
    FILES = {
        "models/comictextdetector.pt": ("comictextdetector.pt", "1f90fa60aeeb1eb82e2ac1167a66bf139a8a61b8780acd351ead55268540cccb"),
        "models/resnet18-f37072fd.pth": ("resnet18-f37072fd.pth", "f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec"),
        "models/anime-manga-big-lama.pt": ("anime-manga-big-lama.pt", "479d3afdcb7ed2fd944ed4ebcc39ca45b33491f0f2e43eb1000bd623cfb41823"),
        "libs/libpatchmatch.so": ("libpatchmatch.so", "dcd2fe308a31cfe2c5e762aadbac68dde516fdaafa598744087a14dcd20c5533"),
        "libs/patchmatch_inpaint.dll": ("patchmatch_inpaint.dll", "0ba60cfe664c97629daa7e4d05c0888ebfe3edcb3feaf1ed5a14544079c6d7af"),
        "libs/opencv_world455.dll": ("opencv_world455.dll", "3b7619caa29dc3352b939de4e9981217a9585a13a756e1101a50c90c100acd8d"),
    }
    
    @classmethod
    def ensure_all(cls):
        data_root = Path(__file__).parent.parent / "data"
        # 创建 Pooch 实例
        pup = pooch.create(
            path=data_root,
            base_url=cls.BASE_URL,
            version=None,           # 禁用版本子目录
        )
        # 自定义 URL 获取：根据本地路径的 basename 拼接 URL
        def get_url(key):
            # key 例如 "models/comictextdetector.pt"
            remote_filename = Path(key).name
            return cls.BASE_URL + remote_filename
        pup.get_url = get_url

        for local_rel_path, (remote_filename, md5) in cls.FILES.items():
            if cls._is_needed(local_rel_path):
                # 注册时使用本地相对路径作为 key
                pup.registry[local_rel_path] = md5
                # fetch 会根据 key 调用 get_url 下载并保存到 data_root/key
                local_file = pup.fetch(local_rel_path)
                # print(f"已就绪: {local_file}")
    
    @staticmethod
    def _is_needed(local_rel_path):
        if ".so" in local_rel_path and not sys.platform.startswith('linux'):
            return False
        if ".dll" in local_rel_path and not sys.platform.startswith('win'):
            return False
        return True
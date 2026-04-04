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

    # 模型文件
    COMIC_TEXT_DETECTOR = MODELS_DIR / "comictextdetector.pt"
    RESNET18 = MODELS_DIR / "resnet18-f37072fd.pth"
    LAMA = MODELS_DIR / "anime-manga-big-lama.pt"

    # 动态库
    PATCHMATCH_SO = LIBS_DIR / "libpatchmatch.so"
    OPENCV_DLL = LIBS_DIR / "opencv_world455.dll"
    PATCHMATCH_INPAINT_DLL = LIBS_DIR / "patchmatch_inpaint.dll"

class InpaintAlgorithm:
    PATCHMATCH = "PatchMatch"
    LAMA = "LaMa"
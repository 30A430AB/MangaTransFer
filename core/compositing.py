import json
from pathlib import Path
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

from PIL import Image
from loguru import logger
from natsort import natsorted

from core.extraction import MaskProcessor
from core.inpainting import Inpainter
from core.config import SUPPORTED_EXTENSIONS, InpaintAlgorithm


# ==================== 辅助函数 ====================

def get_image_files(directory: Path) -> list:
    image_extensions = SUPPORTED_EXTENSIONS
    files = []
    try:
        for entry in directory.iterdir():
            if entry.is_file() and entry.suffix.lower() in image_extensions:
                files.append(entry)
    except FileNotFoundError:
        pass
    return natsorted(files, key=lambda x: x.name)


def find_image_file(directory: Path, base_name: str) -> Path:
    """在目录中查找与基本名称匹配的图片文件"""
    for img_path in get_image_files(directory):
        if img_path.stem == base_name:
            return img_path
    return directory / f"{base_name}.png"


# ==================== 图片尺寸调整 ====================
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from PIL import Image
from loguru import logger

def _resize_worker(raw_path_str, text_path_str):
    """线程工作函数"""
    raw_path = Path(raw_path_str)
    text_path = Path(text_path_str)
    try:
        with Image.open(raw_path) as raw_img:
            raw_height = raw_img.height
        with Image.open(text_path) as text_img:
            ratio = raw_height / text_img.height
            new_width = int(text_img.width * ratio)
            resized = text_img.resize((new_width, raw_height), Image.LANCZOS)
            resized.save(text_path)
        return True
    except Exception as e:
        logger.error(f"调整失败 {text_path.name}: {e}")
        return False

def resize_text_images_to_match_raw(raw_dir, text_dir, status_callback=None):
    """
    多线程版本：调整熟肉图片大小，使其高度与生肉图片相同
    只对匹配成功的图片进行处理，进度条总数 = 匹配数
    """
    raw_images = get_image_files(Path(raw_dir))
    if not raw_images:
        logger.error(f"错误: 生肉目录 {raw_dir} 中没有找到图片文件")
        return 0

    # 构建匹配任务列表（只包含有对应熟肉图片的项）
    tasks = []
    for raw_img_path in raw_images:
        img_stem = raw_img_path.stem
        text_img_path = None
        for candidate in get_image_files(Path(text_dir)):
            if candidate.stem == img_stem:
                text_img_path = candidate
                break
        if text_img_path:
            tasks.append((str(raw_img_path), str(text_img_path)))
        # 没有匹配的图片直接跳过，不加入任务

    if not tasks:
        logger.warning(f"未找到任何匹配的图片对")
        return 0

    total_count = len(tasks)          # 进度条总数 = 实际匹配数
    success_count = 0
    completed = 0

    # 使用多线程，max_workers 可自行调整，默认 CPU 核心数*5
    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(_resize_worker, raw, text): (raw, text) for raw, text in tasks}
        for future in as_completed(futures):
            completed += 1
            if future.result():
                success_count += 1
            if status_callback:
                status_callback(completed, total_count)   # 每完成一个任务就回调一次

    return success_count


def copy_input_images_to_temp(original_input_dir, temp_input_dir):
    """
    将原始输入图片复制到temp目录

    Args:
        original_input_dir: 原始输入目录
        temp_input_dir: temp目录下的输入目录
    """

    os.makedirs(temp_input_dir, exist_ok=True)

    # 遍历获取图片文件
    image_files = get_image_files(Path(original_input_dir))

    copied_count = 0
    for img_path in image_files:
        dest_path = Path(temp_input_dir) / img_path.name
        shutil.copy2(img_path, dest_path)
        copied_count += 1

    return copied_count


# ==================== 文本提取 ====================

def _extract_worker(input_path, mask_path, output_path, dilation_iterations):
    """单个提取任务的工作函数（用于线程池）"""
    try:
        MaskProcessor(
            input_path=input_path,
            mask_path=mask_path,
            output_path=output_path,
            dilation_iterations=dilation_iterations
        )
        return True
    except Exception as e:
        logger.error(f"提取失败 {Path(input_path).name}: {e}")
        return False

def extract_text_from_masks(input_dir, mask_dir, output_dir, dilation_iterations=2, status_callback=None):
    """
    多线程版本：从掩码图像中提取文本
    只处理有对应 mask 的图片，进度条总数 = 实际处理数
    """

    input_images = get_image_files(Path(input_dir))
    if not input_images:
        logger.error(f"错误: 输入目录 {input_dir} 中没有找到图片文件")
        return 0

    # 构建有效任务列表
    tasks = []
    for input_img_path in input_images:
        img_name = input_img_path.stem
        mask_filename = f"mask-{img_name}.png"
        mask_path = Path(mask_dir) / mask_filename
        if not mask_path.exists():
            # 没有 mask 的图片跳过，不计入任务
            continue
        output_path = Path(output_dir) / f"{img_name}.png"
        tasks.append((
            str(input_img_path),
            str(mask_path),
            str(output_path),
            dilation_iterations
        ))

    total = len(tasks)
    if total == 0:
        logger.warning(f"未找到任何有效的 mask 文件，跳过提取")
        return 0

    # 确保输出目录存在
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    success_count = 0
    completed = 0

    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(_extract_worker, *task): task
            for task in tasks
        }
        for future in as_completed(futures):
            completed += 1
            if future.result():
                success_count += 1
            if status_callback:
                status_callback(completed, total)

    return success_count

# ==================== 图像修复 ====================

def inpaint_raw_images(raw_img_dir, new_mask_dir, output_dir, algorithm=InpaintAlgorithm.PATCHMATCH, status_callback=None):
    """
    修复生肉图片

    Args:
        raw_img_dir: 生肉图片目录
        new_mask_dir: 新掩膜目录
        output_dir: 修复结果输出目录
        algorithm: 修复算法，默认使用patchmatch
        status_callback: 进度回调函数
    """

    os.makedirs(output_dir, exist_ok=True)

    raw_images = get_image_files(Path(raw_img_dir))

    if not raw_images:
        logger.error(f"错误: 生肉目录 {raw_img_dir} 中没有找到图片文件")
        return 0

    processed_count = 0
    total_count = len(raw_images)

    for idx, raw_img_path in enumerate(raw_images):
        if status_callback:
            status_callback(idx + 1, total_count)

        img_name = raw_img_path.stem
        mask_filename = f"mask-{img_name}.png"
        mask_path = Path(new_mask_dir) / mask_filename

        if not mask_path.exists():
            continue

        output_filename = f"{img_name}.png"
        output_path = Path(output_dir) / output_filename

        try:
            Inpainter(
                img_path=str(raw_img_path),
                mask_path=str(mask_path),
                output_path=str(output_path),
                algorithm=algorithm,
                debug=False
            )
            processed_count += 1

        except Exception as e:
            logger.error(f"修复失败 {raw_img_path.name}: {e}")

    return processed_count


# ==================== 文本移植 ====================

# ==================== 文本移植 ====================

def _paste_worker(page_name, page_entries, base_dir, status_callback):
    """单个页面的文本贴图任务"""
    try:
        inpainted_dir = base_dir / "inpainted"
        text_dir = base_dir / "temp" / "text"
        result_dir = base_dir / "result"

        # 查找inpainted图片文件
        inpainted_path = find_image_file(inpainted_dir, page_name)
        if not inpainted_path.exists():
            if status_callback:
                status_callback()
            return

        # 查找文本图片文件
        text_path = find_image_file(text_dir, page_name)
        if not text_path.exists():
            # 没有文本图片时，复制原始图片到结果目录
            raw_path = find_image_file(base_dir, page_name)
            if not raw_path.exists():
                if status_callback:
                    status_callback()
                return
            try:
                result_path = result_dir / raw_path.name
                shutil.copy2(raw_path, result_path)
            except Exception as e:
                logger.error(f"复制原始图片 {page_name} 时出错: {str(e)}")
            if status_callback:
                status_callback()
            return

        # 加载inpainted图片
        base_img = Image.open(inpainted_path).convert("RGBA")
        # 加载文本图片
        text_img = Image.open(text_path).convert("RGBA")

        # 处理每个文本块
        for entry in page_entries:
            if entry.get("matched"):
                orig_xyxy = entry["orig_xyxy"]
                xyxy = entry["xyxy"]
                text_block = text_img.crop((
                    orig_xyxy[0], orig_xyxy[1],
                    orig_xyxy[2], orig_xyxy[3]
                ))
                base_img.paste(text_block, (xyxy[0], xyxy[1]), text_block)

        # 保存结果图片
        result_path = result_dir / f"{page_name}.png"
        base_img.save(result_path, "PNG")

    except Exception as e:
        logger.error(f"处理页面 {page_name} 时出错: {str(e)}")

    finally:
        if status_callback:
            status_callback()


def apply_text_to_inpainted(json_data: dict, status_callback=None):
    """多线程版本：将文本块贴到inpainted图片上"""
    base_dir = Path(json_data["directory"])
    result_dir = base_dir / "result"
    os.makedirs(result_dir, exist_ok=True)

    pages = json_data.get("pages", {})
    if not pages:
        return

    # 收集所有页面任务
    tasks = [(page_name, page_entries) for page_name, page_entries in pages.items()]

    # 使用线程池并行处理
    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(_paste_worker, page_name, page_entries, base_dir, status_callback)
            for page_name, page_entries in tasks
        ]
        # 等待所有任务完成（进度回调已在 worker 内触发）
        for future in as_completed(futures):
            # 捕获可能的异常（已在 worker 内捕获并记录）
            pass


def apply_text_to_inpainted_step(json_path, status_callback=None):
    """
    将文字贴到去字后的图片上

    Args:
        json_path: 匹配结果JSON文件路径
        status_callback: 进度回调函数，每处理一张图片调用一次，无参数
    """
    if not os.path.exists(json_path):
        logger.error(f"错误: JSON文件不存在: {json_path}")
        return False

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        apply_text_to_inpainted(json_data, status_callback=status_callback)
        return True
    except Exception as e:
        logger.error(f"文本贴图失败: {e}")
        return False
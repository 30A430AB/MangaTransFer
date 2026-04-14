import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any

from PIL import Image
from loguru import logger
from natsort import natsorted

from core.extraction import MaskProcessor
from core.inpainting import Inpainter
from core.config import SUPPORTED_EXTENSIONS, InpaintAlgorithm

# 常量定义
MASK_PREFIX = "mask-"


# ==================== 辅助函数 ====================

def get_image_files(directory: Path) -> List[Path]:
    """获取目录下所有支持的图片文件，按自然排序"""
    image_extensions = SUPPORTED_EXTENSIONS
    files = []
    try:
        for entry in directory.iterdir():
            if entry.is_file() and entry.suffix.lower() in image_extensions:
                files.append(entry)
    except FileNotFoundError:
        pass
    return natsorted(files, key=lambda x: x.name)


def find_image_file(directory: Path, base_name: str) -> Optional[Path]:
    """在目录中查找与基本名称匹配的图片文件，未找到返回 None"""
    for img_path in get_image_files(directory):
        if img_path.stem == base_name:
            return img_path
    return None


def build_stem_to_path(directory: Path) -> Dict[str, Path]:
    """构建文件名 stem 到路径的映射字典"""
    return {p.stem: p for p in get_image_files(directory)}


# ==================== 图片尺寸调整 ====================

def _resize_worker(raw_path_str: str, text_path_str: str) -> bool:
    """线程工作函数：调整单张图片尺寸"""
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
        logger.exception(f"调整失败 {text_path.name}: {e}")
        return False


def resize_text_images_to_match_raw(
    raw_dir: str,
    text_dir: str,
    status_callback: Optional[Callable[[int, int], None]] = None
) -> int:
    """
    多线程调整熟肉图片大小，使其高度与生肉图片相同。
    只处理有对应熟肉图片的项，进度回调参数为 (已完成数, 总任务数)。
    """
    raw_images = get_image_files(Path(raw_dir))
    if not raw_images:
        logger.error(f"生肉目录 {raw_dir} 中没有找到图片文件")
        return 0

    # 构建熟肉图片 stem → path 映射，加速查找
    text_stem_map = build_stem_to_path(Path(text_dir))

    tasks = []
    for raw_img_path in raw_images:
        stem = raw_img_path.stem
        if stem in text_stem_map:
            tasks.append((str(raw_img_path), str(text_stem_map[stem])))

    if not tasks:
        logger.warning("未找到任何匹配的图片对")
        return 0

    total = len(tasks)
    success_count = 0
    completed = 0

    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(_resize_worker, raw, text): (raw, text) for raw, text in tasks}
        for future in as_completed(futures):
            completed += 1
            if future.result():
                success_count += 1
            if status_callback:
                status_callback(completed, total)

    return success_count


def copy_input_images_to_temp(original_input_dir: str, temp_input_dir: str) -> int:
    """将原始输入图片复制到临时目录"""
    temp_path = Path(temp_input_dir)
    temp_path.mkdir(parents=True, exist_ok=True)

    image_files = get_image_files(Path(original_input_dir))
    copied_count = 0
    for img_path in image_files:
        shutil.copy2(img_path, temp_path / img_path.name)
        copied_count += 1
    return copied_count


# ==================== 文本提取 ====================

def _extract_worker(input_path: str, mask_path: str, output_path: str, dilation_iterations: int) -> bool:
    """单个提取任务的工作函数"""
    try:
        MaskProcessor(
            input_path=input_path,
            mask_path=mask_path,
            output_path=output_path,
            dilation_iterations=dilation_iterations
        )
        return True
    except Exception as e:
        logger.exception(f"提取失败 {Path(input_path).name}: {e}")
        return False


def extract_text_from_masks(
    input_dir: str,
    mask_dir: str,
    output_dir: str,
    dilation_iterations: int = 2,
    status_callback: Optional[Callable[[int, int], None]] = None
) -> int:
    """多线程从掩码图像中提取文本"""
    input_images = get_image_files(Path(input_dir))
    if not input_images:
        logger.error(f"输入目录 {input_dir} 中没有找到图片文件")
        return 0

    tasks = []
    for input_img_path in input_images:
        stem = input_img_path.stem
        mask_path = Path(mask_dir) / f"{MASK_PREFIX}{stem}.png"
        if not mask_path.exists():
            continue
        output_path = Path(output_dir) / f"{stem}.png"
        tasks.append((str(input_img_path), str(mask_path), str(output_path), dilation_iterations))

    total = len(tasks)
    if total == 0:
        logger.warning("未找到任何有效的 mask 文件，跳过提取")
        return 0

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    success_count = 0
    completed = 0

    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(_extract_worker, *task): task for task in tasks}
        for future in as_completed(futures):
            completed += 1
            if future.result():
                success_count += 1
            if status_callback:
                status_callback(completed, total)

    return success_count


# ==================== 图像修复 ====================

def inpaint_raw_images(
    raw_img_dir: str,
    new_mask_dir: str,
    output_dir: str,
    algorithm: InpaintAlgorithm = InpaintAlgorithm.PATCHMATCH,
    status_callback: Optional[Callable[[int, int], None]] = None
) -> int:
    """修复生肉图片，进度回调参数为 (当前处理索引, 总图片数)"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    raw_images = get_image_files(Path(raw_img_dir))
    if not raw_images:
        logger.error(f"生肉目录 {raw_img_dir} 中没有找到图片文件")
        return 0

    processed_count = 0
    total_count = len(raw_images)
    # 用于记录实际进度
    actual_processed = 0

    for raw_img_path in raw_images:
        stem = raw_img_path.stem
        mask_path = Path(new_mask_dir) / f"{MASK_PREFIX}{stem}.png"
        if not mask_path.exists():
            # 没有 mask 时仍需要更新回调（进度条按总数推进）
            actual_processed += 1
            if status_callback:
                status_callback(actual_processed, total_count)
            continue

        output_file = output_path / f"{stem}.png"
        try:
            Inpainter(
                img_path=str(raw_img_path),
                mask_path=str(mask_path),
                output_path=str(output_file),
                algorithm=algorithm,
                debug=False
            )
            processed_count += 1
        except Exception as e:
            logger.exception(f"修复失败 {raw_img_path.name}: {e}")

        actual_processed += 1
        if status_callback:
            status_callback(actual_processed, total_count)

    return processed_count


# ==================== 文本移植 ====================

def _paste_worker(
    page_name: str,
    page_entries: List[Dict[str, Any]],
    base_dir: Path,
    raw_dir: Path,  # 新增：原始生肉目录
    status_callback: Optional[Callable[[], None]] = None
) -> None:
    """单个页面的文本贴图任务，确保无论如何都会调用一次回调"""
    try:
        inpainted_dir = base_dir / "inpainted"
        text_dir = base_dir / "temp" / "text"
        result_dir = base_dir / "result"

        inpainted_path = find_image_file(inpainted_dir, page_name)
        if inpainted_path is None:
            logger.warning(f"找不到修复后图片: {page_name}")
            return

        text_path = find_image_file(text_dir, page_name)
        if text_path is None:
            # 没有文本图片时，复制原始生肉图片到结果目录
            raw_path = find_image_file(raw_dir, page_name)
            if raw_path is not None:
                result_path = result_dir / raw_path.name
                shutil.copy2(raw_path, result_path)
            else:
                logger.warning(f"找不到原始图片: {page_name}")
            return

        # 执行贴图
        base_img = Image.open(inpainted_path).convert("RGBA")
        text_img = Image.open(text_path).convert("RGBA")

        for entry in page_entries:
            if entry.get("matched"):
                orig_xyxy = entry["orig_xyxy"]
                xyxy = entry["xyxy"]
                text_block = text_img.crop((
                    orig_xyxy[0], orig_xyxy[1],
                    orig_xyxy[2], orig_xyxy[3]
                ))
                base_img.paste(text_block, (xyxy[0], xyxy[1]), text_block)

        result_path = result_dir / f"{page_name}.png"
        base_img.save(result_path, "PNG")

    except Exception as e:
        logger.exception(f"处理页面 {page_name} 时出错: {e}")
    finally:
        # 确保无论成功或失败，回调只执行一次
        if status_callback:
            status_callback()


def apply_text_to_inpainted(
    json_data: Dict[str, Any],
    raw_dir: str,  # 新增参数
    status_callback: Optional[Callable[[], None]] = None
) -> None:
    """多线程将文本块贴到修复后的图片上"""
    base_dir = Path(json_data["directory"])
    raw_dir_path = Path(raw_dir)
    result_dir = base_dir / "result"
    result_dir.mkdir(parents=True, exist_ok=True)

    pages = json_data.get("pages", {})
    if not pages:
        return

    with ThreadPoolExecutor() as executor:
        futures = []
        for page_name, page_entries in pages.items():
            future = executor.submit(
                _paste_worker,
                page_name,
                page_entries,
                base_dir,
                raw_dir_path,
                status_callback
            )
            futures.append(future)
        # 等待所有任务完成
        for future in as_completed(futures):
            future.result()  # 若工作函数抛出异常，此处会再次抛出


def apply_text_to_inpainted_step(
    json_path: str,
    raw_dir: str,  # 新增参数
    status_callback: Optional[Callable[[], None]] = None
) -> bool:
    """从 JSON 文件读取数据并执行文本贴图"""
    if not Path(json_path).exists():
        logger.error(f"JSON 文件不存在: {json_path}")
        return False

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        apply_text_to_inpainted(json_data, raw_dir, status_callback)
        return True
    except Exception as e:
        logger.exception(f"文本贴图失败: {e}")
        return False
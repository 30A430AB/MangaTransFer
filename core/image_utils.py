import json
from pathlib import Path
import shutil
from PIL import Image
import os

from core.extraction import MaskProcessor
from core.inpainting import Inpainter


def apply_text_to_inpainted(json_data: dict):
    """将文本块贴到inpainted图片上"""
    # 设置目录路径
    base_dir = Path(json_data["directory"])
    inpainted_dir = base_dir / "inpainted"
    text_dir = base_dir / "text"
    result_dir = base_dir / "result"
    
    # 创建结果目录
    os.makedirs(result_dir, exist_ok=True)
    
    # 逐页处理
    for page_name, page_entries in json_data["pages"].items():
        # 查找inpainted图片文件
        inpainted_path = find_image_file(inpainted_dir, page_name)
        if not inpainted_path.exists():
            print(f"警告: 未找到inpainted图片: {inpainted_path}")
            continue
        
        # 查找文本图片文件
        text_path = find_image_file(text_dir, page_name)
        if not text_path.exists():
            print(f"警告: 未找到文本图片: {text_path}")
            continue
        
        try:
            # 加载inpainted图片
            base_img = Image.open(inpainted_path).convert("RGBA")
            
            # 加载文本图片
            text_img = Image.open(text_path).convert("RGBA")
            
            # 处理每个文本块
            for entry in page_entries:
                if entry["matched"]:
                    # 提取坐标
                    orig_xyxy = entry["orig_xyxy"]  # 在text图片中的原始坐标
                    xyxy = entry["xyxy"]            # 在inpainted图片中的目标坐标
                    
                    # 从文本图片中裁剪文本块
                    text_block = text_img.crop((
                        orig_xyxy[0], orig_xyxy[1],
                        orig_xyxy[2], orig_xyxy[3]
                    ))
                    
                    # 将文本块贴到基础图片上
                    base_img.paste(text_block, (xyxy[0], xyxy[1]), text_block)
            
            # 保存结果图片为PNG格式
            result_path = result_dir / f"{page_name}.png"
            base_img.save(result_path, "PNG")
            print(f"✓ 已合成: {page_name}.png")
            
        except Exception as e:
            print(f"✗ 处理页面 {page_name} 时出错: {str(e)}")

def find_image_file(directory: Path, base_name: str) -> Path:
    """在目录中查找与基本名称匹配的图片文件（支持多种格式）"""
    # 支持的图片格式扩展名
    image_extensions = {'.jpg', '.jpeg', '.png',}
    
    # 尝试查找匹配的文件
    for ext in image_extensions:
        file_path = directory / f"{base_name}{ext}"
        if file_path.exists():
            return file_path
    
    # 如果未找到任何匹配文件，尝试使用目录中的第一个匹配项
    for file in directory.iterdir():
        if file.stem == base_name and file.suffix.lower() in image_extensions:
            return file
    
    # 如果仍未找到，返回默认路径（尽管可能不存在）
    return directory / f"{base_name}.png"

def copy_input_images_to_temp(original_input_dir, temp_input_dir):
    """
    将原始输入图片复制到temp目录
    
    Args:
        original_input_dir: 原始输入目录
        temp_input_dir: temp目录下的输入目录
    """
    print(f"将图片从 {original_input_dir} 复制到 {temp_input_dir}...")
    
    # 确保目标目录存在
    os.makedirs(temp_input_dir, exist_ok=True)
    
    # 支持的图片格式
    image_extensions = {'.jpg', '.jpeg', '.png',}
    
    # 获取所有原始图片 - 使用集合避免重复
    image_files_set = set()
    for ext in image_extensions:
        # 只使用小写扩展名匹配，避免重复
        for img_path in Path(original_input_dir).glob(f"*{ext}"):
            if img_path.is_file():
                image_files_set.add(img_path)
    
    # 转换为列表
    image_files = list(image_files_set)
    
    # 复制图片到temp目录
    copied_count = 0
    for img_path in image_files:
        dest_path = Path(temp_input_dir) / img_path.name
        shutil.copy2(img_path, dest_path)
        copied_count += 1
        print(f"复制: {img_path.name}")
    
    print(f"已复制 {copied_count} 张图片到 {temp_input_dir}")
    return copied_count

def resize_text_images_to_match_raw(raw_dir, text_dir, status_callback=None):
    """
    调整熟肉图片大小，使其高度与生肉图片相同
    
    Args:
        raw_dir: 生肉图片目录
        text_dir: 熟肉图片目录
        status_callback: 进度回调函数
    """
    print("开始调整熟肉图片大小...")
    
    # 支持的图片格式
    image_extensions = {'.jpg', '.jpeg', '.png',}
    
    # 获取所有生肉图片
    raw_images = []
    for ext in image_extensions:
        for img_path in Path(raw_dir).glob(f"*{ext}"):
            if img_path.is_file():
                raw_images.append(img_path)
    
    if not raw_images:
        print(f"错误: 生肉目录 {raw_dir} 中没有找到图片文件")
        return 0
    
    processed_count = 0
    total_count = len(raw_images)
    
    for idx, raw_img_path in enumerate(raw_images):
        if status_callback:
            status_callback(idx + 1, total_count)
        
        # 使用文件名（不含扩展名）来查找对应的熟肉图片
        img_stem = raw_img_path.stem  # 获取不带扩展名的文件名
        
        # 在熟肉目录中查找同名的图片（支持不同扩展名）
        text_img_path = None
        for ext in image_extensions:
            candidate_path = Path(text_dir) / f"{img_stem}{ext}"
            if candidate_path.exists():
                text_img_path = candidate_path
                break
        
        # 检查熟肉图片是否存在
        if text_img_path is None:
            print(f"警告: 未找到熟肉图片 {img_stem}，跳过")
            continue
        
        try:
            # 打开生肉图片获取高度
            with Image.open(raw_img_path) as raw_img:
                raw_height = raw_img.height
            
            # 打开熟肉图片并调整尺寸
            with Image.open(text_img_path) as text_img:
                # 计算新宽度（保持宽高比）
                ratio = raw_height / text_img.height
                new_width = int(text_img.width * ratio)
                
                # 高质量缩放
                resized_img = text_img.resize(
                    (new_width, raw_height),
                    resample=Image.LANCZOS
                )
                
                # 保存调整后的图片（覆盖原文件）
                resized_img.save(text_img_path)
                processed_count += 1
                print(f"✓ 已调整: {text_img_path.name} -> {new_width}x{raw_height}")
                
        except Exception as e:
            print(f"✗ 调整失败 {text_img_path.name}: {e}")
    
    print(f"图片大小调整完成！共处理 {processed_count} 张图片")
    return processed_count

def extract_text_from_masks(input_dir, mask_dir, output_dir, dilation_iterations=2):
    """
    从掩码图像中提取文字
    
    Args:
        input_dir: 原始图片目录
        mask_dir: 掩码图片目录
        output_dir: 提取结果输出目录
        dilation_iterations: 膨胀迭代次数，用于扩大文字区域
    """
    print("开始文字提取...")
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 支持的图片格式
    image_extensions = {'.jpg', '.jpeg', '.png',}
    
    # 获取所有原始图片 - 使用集合避免重复
    input_images_set = set()
    for ext in image_extensions:
        # 只使用小写扩展名匹配，避免重复
        for img_path in Path(input_dir).glob(f"*{ext}"):
            if img_path.is_file():
                input_images_set.add(img_path)
    
    # 转换为列表
    input_images = list(input_images_set)
    
    processed_count = 0
    
    for input_img_path in input_images:
        # 构建对应的掩码文件名 - 使用 mask- 前缀
        img_name = input_img_path.stem
        mask_filename = f"mask-{img_name}.png"
        mask_path = Path(mask_dir) / mask_filename
        
        # 检查掩码文件是否存在
        if not mask_path.exists():
            print(f"警告: 未找到掩码文件 {mask_filename}，跳过 {input_img_path.name}")
            continue
        
        # 构建输出文件名
        output_filename = f"{img_name}.png"
        output_path = Path(output_dir) / output_filename
        
        try:
            # 使用 MaskProcessor 提取文字
            processor = MaskProcessor(
                input_path=str(input_img_path),
                mask_path=str(mask_path),
                output_path=str(output_path),
                dilation_iterations=dilation_iterations
            )
            
            processed_count += 1
            print(f"✓ 已提取: {input_img_path.name} -> {output_filename}")
            
        except Exception as e:
            print(f"✗ 提取失败 {input_img_path.name}: {e}")
    
    print(f"文字提取完成！共处理 {processed_count} 张图片")
    return processed_count

def inpaint_raw_images(raw_img_dir, new_mask_dir, output_dir, algorithm="patchmatch", status_callback=None):
    """
    修复生肉图片
    
    Args:
        raw_img_dir: 生肉图片目录
        new_mask_dir: 新掩膜目录
        output_dir: 修复结果输出目录
        algorithm: 修复算法，默认使用patchmatch
        status_callback: 进度回调函数
    """
    print("开始修复生肉图片...")
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 支持的图片格式
    image_extensions = {'.jpg', '.jpeg', '.png',}
    
    # 获取所有生肉图片
    raw_images = []
    for ext in image_extensions:
        for img_path in Path(raw_img_dir).glob(f"*{ext}"):
            if img_path.is_file():
                raw_images.append(img_path)
    
    if not raw_images:
        print(f"错误: 生肉目录 {raw_img_dir} 中没有找到图片文件")
        return 0
    
    processed_count = 0
    total_count = len(raw_images)
    
    for idx, raw_img_path in enumerate(raw_images):
        if status_callback:
            status_callback(idx + 1, total_count)
        
        # 构建对应的掩膜文件名
        img_name = raw_img_path.stem
        mask_filename = f"mask-{img_name}.png"
        mask_path = Path(new_mask_dir) / mask_filename
        
        # 检查掩膜文件是否存在
        if not mask_path.exists():
            print(f"警告: 未找到掩膜文件 {mask_filename}，跳过 {raw_img_path.name}")
            continue
        
        # 构建输出文件名
        output_filename = f"{img_name}.png"
        output_path = Path(output_dir) / output_filename
        
        try:
            # 使用 Inpainter 进行修复
            inpainter = Inpainter(
                img_path=str(raw_img_path),
                mask_path=str(mask_path),
                output_path=str(output_path),
                algorithm=algorithm,  # 使用patchmatch
                debug=False
            )
            
            processed_count += 1
            print(f"✓ 已修复: {raw_img_path.name} -> {output_filename}")
            
        except Exception as e:
            print(f"✗ 修复失败 {raw_img_path.name}: {e}")
    
    print(f"生肉图片修复完成！共处理 {processed_count} 张图片")
    return processed_count

def apply_text_to_inpainted_step(json_path, status_callback=None):
    """
    第七步：将文字贴到修复后的图片上
    
    Args:
        json_path: 匹配结果JSON文件路径
        status_callback: 进度回调函数
    """
    print("开始将文字贴到修复后的图片上...")
    
    if not os.path.exists(json_path):
        print(f"错误: JSON文件不存在: {json_path}")
        return False
    
    try:
        # 读取JSON数据
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        # 调用贴图函数
        from core.image_utils import apply_text_to_inpainted
        apply_text_to_inpainted(json_data)
        
        return True
        
    except Exception as e:
        print(f"文字贴图失败: {e}")
        return False
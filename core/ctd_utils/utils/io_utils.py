import os.path as osp
import glob
from pathlib import Path
import cv2
import numpy as np
import json

from core.config import SUPPORTED_EXTENSIONS


NP_BOOL_TYPES = (np.bool_, np.bool8)
NP_FLOAT_TYPES = (np.float_, np.float16, np.float32, np.float64)
NP_INT_TYPES = (np.int_, np.int8, np.int16, np.int32, np.int64, np.uint, np.uint8, np.uint16, np.uint32, np.uint64)

# https://stackoverflow.com/questions/26646362/numpy-array-is-not-json-serializable
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.ScalarType):
            if isinstance(obj, NP_BOOL_TYPES):
                return bool(obj)
            elif isinstance(obj, NP_FLOAT_TYPES):
                return float(obj)
            elif isinstance(obj, NP_INT_TYPES):
                return int(obj)
        return json.JSONEncoder.default(self, obj)

def find_all_imgs(img_dir, abs_path=False):
    imglist = list()
    for filep in glob.glob(osp.join(img_dir, "*")):
        filename = osp.basename(filep)
        file_suffix = Path(filename).suffix
        if file_suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if abs_path:
            imglist.append(filep)
        else:
            imglist.append(filename)
    return imglist

def imread(imgpath, read_type=cv2.IMREAD_COLOR):
    # 先尝试 OpenCV 解码（支持常见格式）
    img = cv2.imdecode(np.fromfile(imgpath, dtype=np.uint8), read_type)
    if img is not None:
        return img
    # 回退到 Pillow 读取（支持 AVIF 等）
    try:
        from PIL import Image
        pil_img = Image.open(imgpath)
        if read_type == cv2.IMREAD_COLOR:
            pil_img = pil_img.convert('RGB')
            img = np.array(pil_img)[:, :, ::-1]  # RGB -> BGR
        elif read_type == cv2.IMREAD_GRAYSCALE:
            pil_img = pil_img.convert('L')
            img = np.array(pil_img)
        else:
            # 保留原通道（如 IMREAD_UNCHANGED）
            img = np.array(pil_img)
            # 如果原图是 RGBA，可能需要转换？按需处理
        return img
    except Exception as e:
        print(f"Failed to read image with Pillow: {e}")
        return None

def imwrite(img_path, img, ext='.png'):
    suffix = Path(img_path).suffix
    if suffix != '':
        img_path = img_path.replace(suffix, ext)
    else:
        img_path += ext
    cv2.imencode(ext, img)[1].tofile(img_path)
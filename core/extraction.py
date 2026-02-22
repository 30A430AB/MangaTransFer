from PIL import Image, ImageFilter

class MaskProcessor:
    def __init__(self, input_path: str, mask_path: str, output_path: str = "output.png", dilation_iterations: int = 1):
        self.input_path = input_path
        self.mask_path = mask_path
        self.output_path = output_path
        self.dilation_iterations = dilation_iterations
        self.process()

    def _load_images(self):
        """使用PIL加载图像"""
        self.img = Image.open(self.input_path).convert("RGB")
        self.mask = Image.open(self.mask_path).convert("L")  # 灰度模式

    def _validate_images(self):
        """验证图像有效性"""
        if self.img is None:
            raise ValueError(f"无法加载输入图像: {self.input_path}")
        if self.mask is None:
            raise ValueError(f"无法加载掩膜图像: {self.mask_path}")
        if self.img.size != self.mask.size:
            raise ValueError("输入图像和掩膜尺寸不匹配")

    def _process_mask(self):
        """使用Pillow处理掩膜"""
        # 二值化处理
        binary_mask = self.mask.point(lambda x: 255 if x > 127 else 0)
        
        # 膨胀处理（手动实现）
        kernel = ImageFilter.Kernel((3,3), [1]*9, scale=1)
        self.dilated_mask = binary_mask.copy()
        for _ in range(self.dilation_iterations):
            self.dilated_mask = self.dilated_mask.filter(kernel)
        
        # 创建透明通道
        self.rgba = self.img.copy()
        self.rgba.putalpha(self.dilated_mask)

    def _save_result(self):
        """保存图像"""
        self.rgba.save(self.output_path, format="PNG", optimize=True, compress_level=9, exif=b"")

    def process(self):
        self._load_images()
        self._validate_images()
        self._process_mask()
        self._save_result()
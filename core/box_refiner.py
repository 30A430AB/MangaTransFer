import json
import os
import logging
import numpy as np
import cv2

class CoordinateAdjuster:
    """基于 mask 图像精确调整 match_results.json 中的 orig_xyxy 坐标"""

    def __init__(self, match_results_path: str, text_dir: str, status_callback: callable = None):
        """
        Args:
            match_results_path: match_results.json 文件路径
            text_dir: 存放 mask 图像的目录（即 temp/text，文件名为 {page_name}.png）
            status_callback: 进度回调
            expand_px: 扩展像素
        """
        self.match_results_path = match_results_path
        self.mask_dir = text_dir
        self.status_callback = status_callback
        self.logger = logging.getLogger('CoordinateAdjuster')

    def _expand_bbox(self, bbox, img_shape):
        x1, y1, x2, y2 = bbox
        x1 = max(0, x1 - self.expand_px)
        y1 = max(0, y1 - self.expand_px)
        x2 = x2 + self.expand_px
        y2 = y2 + self.expand_px
        if img_shape is not None:
            h, w = img_shape[:2]
            x2 = min(w, x2)
            y2 = min(h, y2)
        return [int(x1), int(y1), int(x2), int(y2)]

    def _get_text_pixels(self, mask, roi_bbox):
        x1, y1, x2, y2 = map(int, roi_bbox)
        roi = mask[y1:y2, x1:x2]
        if roi.size == 0:
            return np.empty((0, 2), dtype=int)
        if len(roi.shape) == 2:
            ys, xs = np.where(roi > 30)
            pts = np.column_stack((ys, xs))
        elif len(roi.shape) == 3:
            if roi.shape[2] == 4:
                alpha = roi[:, :, 3]
                ys, xs = np.where(alpha > 50)
                if len(ys) == 0:
                    gray = cv2.cvtColor(roi[:, :, :3], cv2.COLOR_BGR2GRAY)
                    ys, xs = np.where(gray > 30)
                pts = np.column_stack((ys, xs))
            else:
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                ys, xs = np.where(gray > 30)
                pts = np.column_stack((ys, xs))
        else:
            pts = np.empty((0, 2), dtype=int)
        return pts

    def _get_min_rect_from_mask(self, mask, roi_bbox):
        pts = self._get_text_pixels(mask, roi_bbox)
        if len(pts) == 0:
            return None, 0
        x1, y1, x2, y2 = map(int, roi_bbox)
        ys, xs = pts[:, 0], pts[:, 1]
        min_y, max_y = np.min(ys), np.max(ys)
        min_x, max_x = np.min(xs), np.max(xs)
        new_x1 = x1 + min_x
        new_y1 = y1 + min_y
        new_x2 = x1 + max_x + 1
        new_y2 = y1 + max_y + 1
        return [int(new_x1), int(new_y1), int(new_x2), int(new_y2)], len(pts)

    def adjust_annotations(self):
        try:
            with open(self.match_results_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            pages = data.get('pages', {})
            total = len(pages)
            processed = 0

            for page_name, entries in pages.items():
                mask_path = os.path.join(self.mask_dir, f"{page_name}.png")
                if not os.path.exists(mask_path):
                    self.logger.warning(f"mask 文件不存在: {mask_path}，跳过 {page_name}")
                    processed += 1
                    if self.status_callback:
                        self.status_callback(processed, total)
                    continue

                mask = cv2.imread(mask_path, cv2.IMREAD_UNCHANGED)
                if mask is None:
                    self.logger.error(f"无法读取 mask: {mask_path}")
                    processed += 1
                    if self.status_callback:
                        self.status_callback(processed, total)
                    continue

                h, w = mask.shape[:2]
                img_shape = (h, w)

                # 动态计算扩展像素：短边的 2% 或至少 5 像素
                short_side = min(h, w)
                expand_px = max(5, short_side // 50)   # 短边除以50 ≈ 2%

                for entry in entries:
                    if 'orig_xyxy' not in entry or not entry['orig_xyxy'] or len(entry['orig_xyxy']) != 4:
                        continue
                    orig_box = entry['orig_xyxy']
                    # 手动扩展
                    x1, y1, x2, y2 = orig_box
                    x1 = max(0, x1 - expand_px)
                    y1 = max(0, y1 - expand_px)
                    x2 = min(w, x2 + expand_px)
                    y2 = min(h, y2 + expand_px)
                    search_roi = [int(x1), int(y1), int(x2), int(y2)]

                    min_rect, _ = self._get_min_rect_from_mask(mask, search_roi)
                    if min_rect is not None:
                        entry['orig_xyxy'] = [int(v) for v in min_rect]

                processed += 1
                if self.status_callback:
                    self.status_callback(processed, total)

            with open(self.match_results_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            self.logger.error(f"坐标调整失败: {str(e)}")
            raise
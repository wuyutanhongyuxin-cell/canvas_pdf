from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat

from deepseek_client import DeepSeekError, is_deepseek_enabled, request_json_completion


def compute_page_metrics(image_path: Path) -> dict[str, Any]:
    with Image.open(image_path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size

        stat = ImageStat.Stat(rgb)
        mean_r, mean_g, mean_b = stat.mean
        std_r, std_g, std_b = stat.stddev
        colorfulness = math.sqrt(std_r ** 2 + std_g ** 2 + std_b ** 2)

        gray = rgb.convert("L")
        histogram = gray.histogram()
        total_pixels = width * height
        white_pixels = sum(histogram[235:256])
        dark_pixels = sum(histogram[:25])
        white_ratio = white_pixels / total_pixels if total_pixels else 0.0
        dark_ratio = dark_pixels / total_pixels if total_pixels else 0.0
        entropy = gray.entropy()

        edge_image = gray.filter(ImageFilter.FIND_EDGES)
        edge_histogram = edge_image.histogram()
        edge_pixels = sum(edge_histogram[48:256])
        edge_ratio = edge_pixels / total_pixels if total_pixels else 0.0

        return {
            "path": str(image_path),
            "width": width,
            "height": height,
            "mean_rgb": [round(mean_r, 2), round(mean_g, 2), round(mean_b, 2)],
            "white_ratio": round(white_ratio, 4),
            "dark_ratio": round(dark_ratio, 4),
            "colorfulness": round(colorfulness, 4),
            "entropy": round(entropy, 4),
            "edge_ratio": round(edge_ratio, 4),
        }


def classify_page(metrics: dict[str, Any]) -> dict[str, Any]:
    white_ratio = metrics["white_ratio"]
    dark_ratio = metrics["dark_ratio"]
    colorfulness = metrics["colorfulness"]
    entropy = metrics["entropy"]
    edge_ratio = metrics["edge_ratio"]

    is_likely_slide = (
        white_ratio >= 0.45
        and edge_ratio >= 0.01
        and colorfulness <= 55
        and dark_ratio <= 0.4
    )
    is_low_information = (
        (white_ratio >= 0.995 and edge_ratio < 0.0031 and entropy < 0.01)
        or (dark_ratio >= 0.995 and edge_ratio < 0.0031 and entropy < 0.01)
    )
    is_likely_photo = (
        white_ratio < 0.28
        and colorfulness > 45
        and edge_ratio < 0.035
    )
    should_drop = is_low_information or is_likely_photo

    reason = "keep"
    if is_low_information:
        reason = "low_information"
    elif is_likely_photo:
        reason = "photo_or_desktop"
    elif not is_likely_slide:
        reason = "non_slide_like_but_kept"

    return {
        **metrics,
        "is_likely_slide": is_likely_slide,
        "is_low_information": is_low_information,
        "is_likely_photo": is_likely_photo,
        "should_drop": should_drop,
        "decision_reason": reason,
    }


def analyze_pages(image_paths: list[Path]) -> list[dict[str, Any]]:
    return [classify_page(compute_page_metrics(path)) for path in image_paths]


def select_pages_to_keep(analyses: list[dict[str, Any]]) -> tuple[list[Path], list[dict[str, Any]]]:
    kept = [Path(item["path"]) for item in analyses if not item["should_drop"]]
    if not kept:
        kept = [Path(item["path"]) for item in analyses]
    return kept, analyses


def build_naming_prompt(
    *,
    original_title: str,
    source_url: str,
    page_analyses: list[dict[str, Any]],
    kept_count: int,
    dropped_count: int,
) -> str:
    sample = page_analyses[:5]
    return (
        "请基于以下课件信息，生成一个适合 Windows 文件名的简洁中文 PDF 标题。"
        "输出 JSON，字段必须包含 suggested_title 和 reasoning。"
        f"\noriginal_title: {original_title}"
        f"\nsource_url: {source_url}"
        f"\nkept_count: {kept_count}"
        f"\ndropped_count: {dropped_count}"
        f"\npage_samples: {sample}"
    )


def suggest_title_with_deepseek(
    *,
    original_title: str,
    source_url: str,
    page_analyses: list[dict[str, Any]],
    kept_count: int,
    dropped_count: int,
) -> dict[str, Any]:
    if not is_deepseek_enabled():
        return {
            "used_deepseek": False,
            "suggested_title": original_title,
            "reasoning": "DEEPSEEK_API_KEY 未设置，跳过命名增强",
        }

    system_prompt = (
        "你是一个课件整理助手。"
        "你的任务是根据输入元数据给 PDF 生成尽量准确、简洁、可读的中文文件名。"
        "必须返回 JSON 对象。suggested_title 不要包含扩展名，不要包含 Windows 非法文件名字符。"
    )
    user_prompt = build_naming_prompt(
        original_title=original_title,
        source_url=source_url,
        page_analyses=page_analyses,
        kept_count=kept_count,
        dropped_count=dropped_count,
    )
    result = request_json_completion(system_prompt=system_prompt, user_prompt=user_prompt)

    suggested = str(result.get("suggested_title") or original_title).strip()
    return {
        "used_deepseek": True,
        "suggested_title": suggested or original_title,
        "reasoning": result.get("reasoning") or "",
    }

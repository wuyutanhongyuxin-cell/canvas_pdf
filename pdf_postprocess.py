from __future__ import annotations

import math
import re
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

        center_box = (
            int(width * 0.2),
            int(height * 0.15),
            int(width * 0.8),
            int(height * 0.85),
        )
        left_box = (
            0,
            0,
            int(width * 0.12),
            height,
        )

        center_gray = gray.crop(center_box)
        left_gray = gray.crop(left_box)

        center_total = center_gray.size[0] * center_gray.size[1]
        left_total = left_gray.size[0] * left_gray.size[1]

        center_edge_histogram = center_gray.filter(ImageFilter.FIND_EDGES).histogram()
        left_edge_histogram = left_gray.filter(ImageFilter.FIND_EDGES).histogram()

        blue_dominance = mean_b - max(mean_r, mean_g)

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
            "center_entropy": round(center_gray.entropy(), 4),
            "center_edge_ratio": round(sum(center_edge_histogram[48:256]) / center_total, 4) if center_total else 0.0,
            "left_entropy": round(left_gray.entropy(), 4),
            "left_edge_ratio": round(sum(left_edge_histogram[48:256]) / left_total, 4) if left_total else 0.0,
            "blue_dominance": round(blue_dominance, 4),
        }


def classify_page(metrics: dict[str, Any]) -> dict[str, Any]:
    white_ratio = metrics["white_ratio"]
    dark_ratio = metrics["dark_ratio"]
    colorfulness = metrics["colorfulness"]
    entropy = metrics["entropy"]
    edge_ratio = metrics["edge_ratio"]
    center_entropy = metrics["center_entropy"]
    center_edge_ratio = metrics["center_edge_ratio"]
    left_entropy = metrics["left_entropy"]
    left_edge_ratio = metrics["left_edge_ratio"]
    blue_dominance = metrics["blue_dominance"]

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
    is_desktop_wallpaper = (
        center_entropy < 3.45
        and center_edge_ratio < 0.05
        and left_entropy > center_entropy + 0.25
        and left_edge_ratio > center_edge_ratio * 1.45
        and blue_dominance > 30
    )
    should_drop = is_low_information or is_likely_photo or is_desktop_wallpaper

    reason = "keep"
    if is_low_information:
        reason = "low_information"
    elif is_desktop_wallpaper:
        reason = "desktop_wallpaper"
    elif is_likely_photo:
        reason = "photo_or_desktop"
    elif not is_likely_slide:
        reason = "non_slide_like_but_kept"

    return {
        **metrics,
        "is_likely_slide": is_likely_slide,
        "is_low_information": is_low_information,
        "is_likely_photo": is_likely_photo,
        "is_desktop_wallpaper": is_desktop_wallpaper,
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
    page_title: str,
    course_title: str,
    lecture_label: str,
    page_analyses: list[dict[str, Any]],
    kept_count: int,
    dropped_count: int,
) -> str:
    sample = page_analyses[:5]
    return (
        "请基于以下课件信息，生成一个适合 Windows 文件名的简洁中文 PDF 标题。"
        "输出 JSON，字段必须包含 suggested_title 和 reasoning。"
        f"\noriginal_title: {original_title}"
        f"\npage_title: {page_title}"
        f"\ncourse_title: {course_title}"
        f"\nlecture_label: {lecture_label}"
        f"\nsource_url: {source_url}"
        f"\nkept_count: {kept_count}"
        f"\ndropped_count: {dropped_count}"
        f"\npage_samples: {sample}"
    )


def normalize_title_piece(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    text = re.sub(r"[\\/:*?\"<>|]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_lecture_label(*candidates: str) -> str:
    pattern = re.compile(r"第\s*0*(\d{1,3})\s*讲")
    for candidate in candidates:
        match = pattern.search(candidate or "")
        if match:
            return f"第{int(match.group(1)):02d}讲"
    return ""


def build_fallback_title(
    *,
    original_title: str,
    page_title: str,
    course_title: str,
    lecture_label: str,
    kept_count: int,
) -> str:
    lecture = extract_lecture_label(lecture_label, page_title, original_title)
    course = normalize_title_piece(course_title) or normalize_title_piece(page_title) or normalize_title_piece(original_title) or "课件"
    course = re.sub(r"第\s*0*\d+\s*讲", "", course).strip(" -_")

    pieces = [piece for piece in [course, lecture] if piece]
    if not pieces:
        pieces = ["课件"]
    return f"{'_'.join(pieces)}_{kept_count}页保留"


def suggest_title_with_deepseek(
    *,
    original_title: str,
    source_url: str,
    page_title: str,
    course_title: str,
    lecture_label: str,
    page_analyses: list[dict[str, Any]],
    kept_count: int,
    dropped_count: int,
) -> dict[str, Any]:
    fallback_title = build_fallback_title(
        original_title=original_title,
        page_title=page_title,
        course_title=course_title,
        lecture_label=lecture_label,
        kept_count=kept_count,
    )

    if not is_deepseek_enabled():
        return {
            "used_deepseek": False,
            "suggested_title": fallback_title,
            "reasoning": "DEEPSEEK_API_KEY 未设置，跳过命名增强",
            "deepseek_error": "",
        }

    system_prompt = (
        "你是一个课件整理助手。"
        "你的任务是根据输入元数据给 PDF 生成尽量准确、简洁、可读的中文文件名。"
        "必须返回 JSON 对象。suggested_title 不要包含扩展名，不要包含 Windows 非法文件名字符。"
    )
    user_prompt = build_naming_prompt(
        original_title=original_title,
        source_url=source_url,
        page_title=page_title,
        course_title=course_title,
        lecture_label=lecture_label,
        page_analyses=page_analyses,
        kept_count=kept_count,
        dropped_count=dropped_count,
    )
    try:
        result = request_json_completion(system_prompt=system_prompt, user_prompt=user_prompt)
    except Exception as error:
        return {
            "used_deepseek": False,
            "suggested_title": fallback_title,
            "reasoning": "DeepSeek 调用失败，已回退到本地命名",
            "deepseek_error": str(error),
        }

    suggested = str(result.get("suggested_title") or original_title).strip()
    return {
        "used_deepseek": True,
        "suggested_title": suggested or fallback_title,
        "reasoning": result.get("reasoning") or "",
        "deepseek_error": "",
    }

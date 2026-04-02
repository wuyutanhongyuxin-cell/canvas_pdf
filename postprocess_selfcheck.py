from __future__ import annotations

import tempfile
from pathlib import Path
import os

from PIL import Image, ImageDraw

from pdf_postprocess import analyze_pages, build_fallback_title, select_pages_to_keep, suggest_title_with_deepseek


def create_blank_slide(path: Path) -> None:
    Image.new("RGB", (1920, 1080), (255, 255, 255)).save(path, quality=95)


def create_text_slide(path: Path) -> None:
    image = Image.new("RGB", (1920, 1080), (250, 250, 250))
    draw = ImageDraw.Draw(image)
    draw.text((300, 200), "Language and Cognition", fill=(0, 0, 0))
    draw.text((300, 320), "Lecture 1", fill=(0, 0, 0))
    image.save(path, quality=95)
    image.close()


def create_photo_page(path: Path) -> None:
    image = Image.new("RGB", (1920, 1080), (40, 90, 180))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 650, 1920, 1080), fill=(80, 70, 50))
    draw.ellipse((1300, 120, 1750, 570), fill=(90, 160, 80))
    image.save(path, quality=95)
    image.close()


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old_cwd = Path.cwd()
        blank = root / "blank.jpg"
        slide = root / "slide.jpg"
        photo = root / "photo.jpg"

        create_blank_slide(blank)
        create_text_slide(slide)
        create_photo_page(photo)
        try:
            os.chdir(root)
            analyses = analyze_pages([blank, slide, photo])
            kept, full = select_pages_to_keep(analyses)

            by_name = {Path(item["path"]).name: item for item in full}
            assert by_name["blank.jpg"]["should_drop"] is True
            assert by_name["slide.jpg"]["should_drop"] is False
            assert by_name["photo.jpg"]["should_drop"] is True
            assert [path.name for path in kept] == ["slide.jpg"]

            naming = suggest_title_with_deepseek(
                original_title="PPT",
                source_url="https://v.sjtu.edu.cn/course/1",
                page_title="日语精读（6） - 第10讲",
                course_title="日语精读（6）",
                lecture_label="第10讲",
                page_analyses=full,
                kept_count=1,
                dropped_count=2,
            )
            assert naming["used_deepseek"] is False
            assert naming["suggested_title"] == "日语精读（6）_第10讲_1页保留"
            assert build_fallback_title(
                original_title="PPT",
                page_title="语言与认知 - 第05讲",
                course_title="语言与认知",
                lecture_label="第05讲",
                kept_count=4,
            ) == "语言与认知_第05讲_4页保留"
        finally:
            os.chdir(old_cwd)

    print("postprocess selfcheck passed")


if __name__ == "__main__":
    main()

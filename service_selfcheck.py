from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image

import local_pdf_service
from local_pdf_service import build_pdf_from_paths, create_pdf_job, make_unique_file_path, sanitize_filename


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def create_sample_image(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", size, color)
    image.save(path, quality=95)
    image.close()


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        img1 = root / "slide_001.jpg"
        img2 = root / "slide_002.jpg"
        pdf_path = root / "课件 第1讲.pdf"

        create_sample_image(img1, (1920, 1080), (20, 40, 180))
        create_sample_image(img2, (1920, 1080), (180, 80, 20))

        result = build_pdf_from_paths([img1, img2], pdf_path)
        duplicate_path = make_unique_file_path(pdf_path)

        assert_true(sanitize_filename('课程: 第/1讲?') == '课程 第 1讲', "sanitize_filename failed")
        assert_true(result["page_count"] == 2, "build_pdf_from_paths page_count failed")
        assert_true(pdf_path.exists(), "PDF was not created")
        assert_true(pdf_path.stat().st_size > 0, "PDF is empty")
        assert_true(duplicate_path.name == "课件 第1讲_2.pdf", "make_unique_file_path failed")

        blank = root / "slide_003.jpg"
        create_sample_image(blank, (1920, 1080), (255, 255, 255))

        original_download_images = local_pdf_service.download_images
        original_suggest_title = local_pdf_service.suggest_title_with_deepseek
        try:
            local_pdf_service.download_images = lambda urls, workspace: [img1, img2, blank]
            local_pdf_service.suggest_title_with_deepseek = lambda **kwargs: {
                "used_deepseek": True,
                "suggested_title": "语言与认知 第1讲",
                "reasoning": "mock",
            }
            job_result = create_pdf_job(
                title="PPT",
                urls=["https://example.com/1.jpg"],
                output_dir=root / "exports",
                source_url="https://v.sjtu.edu.cn/course/1",
            )
        finally:
            local_pdf_service.download_images = original_download_images
            local_pdf_service.suggest_title_with_deepseek = original_suggest_title

        assert_true(job_result["title"] == "语言与认知 第1讲", "create_pdf_job title enhancement failed")
        assert_true(job_result["page_count"] == 2, "create_pdf_job should keep two pages after filtering")
        assert_true(job_result["dropped_count"] == 1, "create_pdf_job should report dropped pages")
        assert_true(job_result["used_deepseek"] is True, "create_pdf_job should report DeepSeek usage")
        assert_true(Path(job_result["pdf_path"]).exists(), "create_pdf_job should output a PDF")

    print("service selfcheck passed")


if __name__ == "__main__":
    main()

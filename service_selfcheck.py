from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image

from local_pdf_service import build_pdf_from_paths, make_unique_file_path, sanitize_filename


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

    print("service selfcheck passed")


if __name__ == "__main__":
    main()

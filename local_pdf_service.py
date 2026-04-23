from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
import time
import urllib.parse
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable

import requests
from PIL import Image

from pdf_postprocess import analyze_pages, select_pages_to_keep, suggest_title_with_deepseek


HOST = "127.0.0.1"
PORT = 38765
DOWNLOAD_TIMEOUT = (15, 90)
DOWNLOAD_RETRIES = 3
DOWNLOAD_RETRY_BACKOFF = 2.0
DEFAULT_OUTPUT_DIR = Path(r"E:\zhiwang_text\canvas_course")
USER_AGENT = "sjtu-pdf-local-service/1.0"


def sanitize_filename(raw: str, fallback: str = "课件") -> str:
    normalized = "".join(" " if char in '\\/:*?"<>|' else char for char in str(raw or ""))
    normalized = " ".join(normalized.split()).strip()
    return (normalized or fallback)[:80]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_unique_file_path(base_path: Path) -> Path:
    if not base_path.exists():
        return base_path

    stem = base_path.stem
    suffix = base_path.suffix
    parent = base_path.parent
    index = 2

    while True:
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def guess_extension(content_type: str, url: str) -> str:
    source = f"{content_type or ''} {url or ''}".lower()
    if "png" in source:
      return ".png"
    if "webp" in source:
      return ".webp"
    if "jpeg" in source or "jpg" in source:
      return ".jpg"
    return ".img"


def download_image(url: str, output_path: Path, session: requests.Session) -> Path:
    last_error: Exception | None = None
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            response = session.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
            response.raise_for_status()
            with output_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        handle.write(chunk)
            return output_path
        except (requests.Timeout, requests.ConnectionError) as error:
            last_error = error
            if attempt < DOWNLOAD_RETRIES:
                time.sleep(min(DOWNLOAD_RETRY_BACKOFF ** attempt, 8.0))
    assert last_error is not None
    raise last_error


def download_images(urls: Iterable[str], workspace: Path) -> list[Path]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.trust_env = False

    downloaded_paths: list[Path] = []
    for index, url in enumerate(urls, start=1):
        extension = guess_extension("", url)
        parsed = urllib.parse.urlparse(url)
        if parsed.path:
            extension = guess_extension("", parsed.path) or extension
        output_path = workspace / f"slide_{index:03d}{extension}"
        downloaded_paths.append(download_image(url, output_path, session))
    return downloaded_paths


def build_pdf_from_paths(image_paths: Iterable[Path], pdf_path: Path) -> dict:
    converted_images = []
    sources = []

    try:
        for image_path in image_paths:
            with Image.open(image_path) as image:
                converted = image.convert("RGB")
                converted_images.append(converted)
                sources.append(str(image_path))

        if not converted_images:
            raise ValueError("未找到可用于合成 PDF 的图片")

        first, rest = converted_images[0], converted_images[1:]
        first.save(
            pdf_path,
            save_all=True,
            append_images=rest,
            resolution=150.0,
        )
        return {
            "page_count": len(converted_images),
            "pdf_path": str(pdf_path),
            "sources": sources,
        }
    finally:
        for image in converted_images:
            image.close()


def create_pdf_job(title: str, urls: list[str], output_dir: Path | None = None, source_url: str = "", subfolder: str = "") -> dict:
    if not urls:
        raise ValueError("图片 URL 列表为空")

    page_title = ""
    course_title = ""
    lecture_label = ""
    if isinstance(title, dict):
        page_title = str(title.get("pageTitle") or "")
        course_title = str(title.get("courseTitle") or "")
        lecture_label = str(title.get("lectureLabel") or "")
        safe_title = sanitize_filename(title.get("originalTitle") or title.get("title") or "课件")
    else:
        safe_title = sanitize_filename(title)
    base_dir = output_dir or DEFAULT_OUTPUT_DIR
    safe_subfolder = sanitize_filename(subfolder, fallback="") if subfolder else ""
    target_dir = ensure_dir(base_dir / safe_subfolder if safe_subfolder else base_dir)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    workspace = ensure_dir(target_dir / f"{safe_title}-{timestamp}")

    image_paths = download_images(urls, workspace)
    page_analyses = analyze_pages(image_paths)
    kept_paths, full_analyses = select_pages_to_keep(page_analyses)
    title_result = suggest_title_with_deepseek(
        original_title=safe_title,
        source_url=source_url,
        page_title=page_title,
        course_title=course_title,
        lecture_label=lecture_label,
        page_analyses=full_analyses,
        kept_count=len(kept_paths),
        dropped_count=len(image_paths) - len(kept_paths),
    )
    final_title = sanitize_filename(title_result["suggested_title"], fallback=safe_title)
    pdf_path = make_unique_file_path(target_dir / f"{final_title}.pdf")
    build_result = build_pdf_from_paths(kept_paths, pdf_path)
    return {
        "ok": True,
        "title": final_title,
        "original_title": safe_title,
        "page_count": build_result["page_count"],
        "pdf_path": build_result["pdf_path"],
        "workspace": str(workspace),
        "image_count": len(image_paths),
        "dropped_count": len(image_paths) - len(kept_paths),
        "used_deepseek": title_result["used_deepseek"],
        "deepseek_reasoning": title_result["reasoning"],
        "deepseek_error": title_result.get("deepseek_error", ""),
        "lecture_label": lecture_label,
        "page_analyses": full_analyses,
    }


@dataclass
class ServiceConfig:
    output_dir: Path


class PdfJobHandler(BaseHTTPRequestHandler):
    server_version = "SJTU-PDF-Service/1.0"

    @property
    def config(self) -> ServiceConfig:
        return self.server.config  # type: ignore[attr-defined]

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.startswith("/health"):
            self._write_json(HTTPStatus.OK, {"ok": True, "service": "sjtu-pdf-local-service"})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if not self.path.startswith("/jobs"):
            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return

        try:
            payload = self._read_json()
            result = create_pdf_job(
                title=payload.get("title") or "课件",
                urls=list(payload.get("imageUrls") or []),
                output_dir=self.config.output_dir,
                source_url=payload.get("sourceUrl") or "",
                subfolder=payload.get("subfolder") or "",
            )
        except Exception as error:  # noqa: BLE001
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(error)})
            return

        self._write_json(HTTPStatus.OK, result)

    def log_message(self, format_: str, *args) -> None:  # noqa: A003
        print("[local-pdf-service]", format_ % args)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            raise ValueError("请求体为空")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _set_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")

    def _write_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_server(output_dir: Path, host: str = HOST, port: int = PORT) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), PdfJobHandler)
    server.config = ServiceConfig(output_dir=ensure_dir(output_dir))  # type: ignore[attr-defined]
    return server


def serve(output_dir: Path, host: str = HOST, port: int = PORT) -> None:
    server = create_server(output_dir=output_dir, host=host, port=port)
    print(f"[local-pdf-service] listening on http://{host}:{port}")
    print(f"[local-pdf-service] output dir: {output_dir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SJTU local high-quality PDF builder service")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    serve(output_dir=args.output_dir, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

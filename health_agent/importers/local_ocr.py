from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from health_agent.errors import OcrUnavailable, ValidationFailure

_VISION_OCR_SOURCE = r'''
import AppKit
import Foundation
import PDFKit
import Vision

struct PageResult: Codable {
    let page: Int
    let text: String
    let confidence: Float
}

guard CommandLine.arguments.count == 2 else {
    FileHandle.standardError.write(Data("missing PDF path\n".utf8))
    exit(2)
}

let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let document = PDFDocument(url: url) else {
    FileHandle.standardError.write(Data("cannot open PDF\n".utf8))
    exit(3)
}

if document.pageCount > 20 {
    FileHandle.standardError.write(Data("PDF page limit exceeded\n".utf8))
    exit(4)
}

var results: [PageResult] = []
for index in 0..<document.pageCount {
    guard let page = document.page(at: index) else { continue }
    let bounds = page.bounds(for: .mediaBox)
    let longest = max(bounds.width, bounds.height)
    let scale = min(3.0, 2400.0 / max(longest, 1.0))
    let size = NSSize(width: bounds.width * scale, height: bounds.height * scale)
    let image = page.thumbnail(of: size, for: .mediaBox)
    guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        continue
    }

    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = true
    request.customWords = ["颏下", "颌下", "淋巴结", "皮髓质", "门型血流"]
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    try handler.perform([request])
    let observations = (request.results ?? []).sorted {
        if abs($0.boundingBox.midY - $1.boundingBox.midY) > 0.01 {
            return $0.boundingBox.midY > $1.boundingBox.midY
        }
        return $0.boundingBox.minX < $1.boundingBox.minX
    }
    let candidates = observations.compactMap { $0.topCandidates(1).first }
    let text = candidates.map { $0.string }.joined(separator: "\n")
    let confidence: Float = candidates.isEmpty
        ? 0.0
        : candidates.map { $0.confidence }.reduce(0.0, +) / Float(candidates.count)
    results.append(PageResult(page: index + 1, text: text, confidence: confidence))
}

let data = try JSONEncoder().encode(results)
FileHandle.standardOutput.write(data)
'''


@dataclass(frozen=True)
class OcrResult:
    text: str
    mean_confidence: float
    page_count: int
    engine: str


def ocr_pdf_locally(path: Path) -> OcrResult:
    if path.suffix.lower() != ".pdf":
        raise ValidationFailure("Local report OCR currently supports PDF files only")
    swift = shutil.which("swift")
    if swift is None:
        raise OcrUnavailable(
            "No supported local OCR engine is available; no report data was sent externally."
        )
    try:
        result = subprocess.run(  # noqa: S603 - resolved local executable path.
            [swift, "-", str(path)],
            input=_VISION_OCR_SOURCE,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        raise OcrUnavailable("The local OCR engine timed out; no data was sent externally") from exc
    if result.returncode != 0:
        raise OcrUnavailable(
            "The local macOS Vision OCR engine could not read this PDF; "
            "no data was sent externally."
        )
    try:
        pages = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise OcrUnavailable("The local OCR engine returned an invalid response") from exc
    text_parts = [str(page.get("text") or "").strip() for page in pages]
    text_parts = [part for part in text_parts if part]
    confidences = [float(page.get("confidence") or 0.0) for page in pages if page.get("text")]
    return OcrResult(
        text="\n".join(text_parts),
        mean_confidence=sum(confidences) / len(confidences) if confidences else 0.0,
        page_count=len(pages),
        engine="macos-vision-ocr",
    )

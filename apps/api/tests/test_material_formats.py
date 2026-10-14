import base64
import io

import pytest
from PIL import Image
from pypdf import PdfWriter

from app.domain.documents import office_pdf
from app.material_analysis import sections


@pytest.mark.parametrize(
    "extension,format",
    [("png", "PNG"), ("jpg", "JPEG"), ("gif", "GIF"), ("tiff", "TIFF"), ("bmp", "BMP"), ("webp", "WEBP")],
)
def test_image_contents_normalized(tmp_path, extension, format):
    source = tmp_path / ("original." + extension)
    Image.new("RGB", (50, 40), "red").save(source, format=format)
    label, parts = list(sections(source, "image/" + extension, tmp_path))[0]
    assert "frame/page 1" in label
    image = Image.open(io.BytesIO(base64.b64decode(parts[0]["inlineData"]["data"])))
    assert image.size == (50, 40)


def test_pdf_all_pages_and_html(tmp_path):
    source = tmp_path / "scan.pdf"
    pdf = PdfWriter()
    for _ in range(3):
        pdf.add_blank_page(width=100, height=100)
    pdf.write(source)
    assert len(list(sections(source, "application/pdf", tmp_path))) == 3
    source = tmp_path / "article.html"
    source.write_text("<h1>Family story</h1><script>malicious()</script><p>A garden</p>")
    result = list(sections(source, "text/html", tmp_path))
    assert result[0][1][0]["text"] == "Family story\nA garden"


def test_office_conversion_rtf(tmp_path):
    import shutil

    if not shutil.which("libreoffice"):
        pytest.skip("requires converter image")
    source = tmp_path / "article.rtf"
    source.write_text(r"{\rtf1\ansi A family garden article.}")
    assert office_pdf(source, tmp_path).read_bytes().startswith(b"%PDF")

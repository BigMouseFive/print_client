"""外箱标签 PDF 裁剪（从 windows_print_agent.py 原样迁移）"""

from io import BytesIO

from pypdf import PdfReader, PdfWriter
from reportlab.lib.units import mm


def crop_pdf_to_size(pdf_bytes: bytes, width_mm: float = 100, height_mm: float = 100) -> bytes:
    """
    将 PDF 裁剪为指定尺寸：从左边和上边各裁剪指定毫米数后，获取目标尺寸区域
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()

    # 裁剪偏移量（左 5mm，上 5mm）
    crop_left = 5 * mm
    crop_top = 5 * mm

    target_width = width_mm * mm
    target_height = height_mm * mm

    for page in reader.pages:
        mediabox = page.mediabox
        original_width = mediabox.upper_right[0] - mediabox.lower_left[0]
        original_height = mediabox.upper_right[1] - mediabox.lower_left[1]

        new_lower_left_x = crop_left
        new_lower_left_y = original_height - crop_top - target_height
        new_upper_right_x = crop_left + target_width
        new_upper_right_y = original_height - crop_top

        page.mediabox.lower_left = (new_lower_left_x, new_lower_left_y)
        page.mediabox.upper_right = (new_upper_right_x, new_upper_right_y)

        writer.add_page(page)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def crop_pdf_to_size_if_needed(pdf_bytes: bytes, width_mm: float = 100, height_mm: float = 100) -> bytes:
    """
    检测 PDF 尺寸，如果超过目标尺寸则裁剪，否则返回原 PDF
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    if not reader.pages:
        return pdf_bytes

    first_page = reader.pages[0]
    mediabox = first_page.mediabox

    pdf_width_pt = mediabox.upper_right[0] - mediabox.lower_left[0]
    pdf_height_pt = mediabox.upper_right[1] - mediabox.lower_left[1]

    target_width_pt = width_mm * mm
    target_height_pt = height_mm * mm

    if pdf_width_pt <= target_width_pt and pdf_height_pt <= target_height_pt:
        return pdf_bytes

    return crop_pdf_to_size(pdf_bytes, width_mm, height_mm)

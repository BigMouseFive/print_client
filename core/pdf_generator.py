"""FNSKU 标签 PDF 生成（从 windows_print_agent.py 原样迁移）"""

from io import BytesIO

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import barcode
from barcode.writer import ImageWriter
from PIL import Image


def generate_fnsku_pdf(fnsku: str, sku: str, origin: str, copies: int = 1) -> bytes:
    """
    生成 FNSKU 标签 PDF
    布局（从上到下）：条形码 -> FNSKU -> 分隔线 -> SKU -> origin(made in china)
    整体位置：靠近标签底部
    """
    W, H = 60 * mm, 40 * mm

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))

    # 生成条形码
    bc_io = BytesIO()
    barcode.get("code128", fnsku, writer=ImageWriter()).write(
        bc_io,
        options={
            "module_width": 0.35,
            "module_height": 15.0,
            "font_size": 0,
            "quiet_zone": 1.5,
            "write_text": False,
        },
    )
    bc_io.seek(0)
    img = Image.open(bc_io)
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    cropped = BytesIO()
    img.save(cropped, format="PNG")
    cropped.seek(0)

    # 布局参数
    mx = 2.5 * mm      # 左右边距
    bh = 20 * mm       # 条形码高度
    bottom_margin = 3 * mm  # 底部边距

    # 从底部向上布局
    y = bottom_margin

    # 1. origin（最底部）
    c.setFont("Helvetica", 7)
    c.drawCentredString(W / 2, y, origin)
    y += 4 * mm

    # 2. SKU
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(W / 2, y, sku)
    y += 5 * mm

    # 3. 分隔线
    c.setLineWidth(0.5)
    c.line(mx, y, W - mx, y)
    y += 4 * mm

    # 4. FNSKU
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(W / 2, y, fnsku)
    y += 4 * mm

    # 5. 条形码（最顶部）
    c.drawImage(
        ImageReader(cropped),
        x=mx,
        y=y,
        width=W - 2 * mx,
        height=bh,
        preserveAspectRatio=False,
    )

    c.save()
    return buf.getvalue()

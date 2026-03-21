"""
佳博打印代理服务 - 完整版
=====================================
运行环境：Windows（接打印机的电脑）
访问地址：http://localhost:5050

依赖安装：
    pip install flask reportlab python-barcode[images] Pillow openpyxl

启动：
    python windows_print_agent.py

开机自启：
    新建 start_print_agent.bat，内容：
        @echo off
        cd /d C:\你的脚本目录
        python windows_print_agent.py
    按 Win+R 输入 shell:startup，把该 bat 文件放入其中。
"""

import os, sys, json, tempfile, threading, subprocess, time, base64
from datetime import datetime
from io import BytesIO
from flask import Flask, request, jsonify, Response

try:
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    import barcode
    from barcode.writer import ImageWriter
    from PIL import Image
    from pypdf import PdfReader, PdfWriter
    from io import BytesIO
except ImportError as e:
    print(f"[错误] 缺少依赖，请运行：\n  pip install flask reportlab python-barcode[images] Pillow openpyxl pypdf\n{e}")
    sys.exit(1)

app = Flask(__name__)


# 提供 JS 文件
@app.route("/app.js")
def serve_js():
    js_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.js")
    with open(js_path, "r", encoding="utf-8") as f:
        return Response(f.read(), mimetype="application/javascript")

# ═══════════════════════════════════════════════════════
# 配置 — 仅需修改这里
# ═══════════════════════════════════════════════════════
PORT          = 5050
FNSKU_PRINTER = "Gprinter GP-1326D"   # 改为 Windows「设备和打印机」中的实际名称
BOX_PRINTER   = "Gprinter GP-1326D"   # 外箱标签打印机（同一台则填一样）

SUMATRA_PATHS = [
    r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
    r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "SumatraPDF", "SumatraPDF.exe"),
]
# ═══════════════════════════════════════════════════════

print_log = []   # 内存日志，最近100条


# ───────────────────────────────────────────────────────
# 打印核心
# ───────────────────────────────────────────────────────

def get_sumatra():
    for p in SUMATRA_PATHS:
        if os.path.exists(p):
            return p
    return None


def crop_pdf_to_size(pdf_bytes: bytes, width_mm: float = 100, height_mm: float = 100) -> bytes:
    """
    将PDF裁剪为指定尺寸（左上角），支持多页
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()

    target_width = width_mm * mm
    target_height = height_mm * mm

    for page in reader.pages:
        # 创建目标尺寸的新页面
        page.mediabox.upper_left = (target_width, target_height)
        writer.add_page(page)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def crop_pdf_to_size_if_needed(pdf_bytes: bytes, width_mm: float = 100, height_mm: float = 100) -> bytes:
    """
    检测PDF尺寸，如果超过目标尺寸则裁剪，否则返回原PDF
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    if not reader.pages:
        return pdf_bytes

    # 获取第一页的尺寸（PDF单位是点，1mm ≈ 2.83点）
    first_page = reader.pages[0]
    mediabox = first_page.mediabox

    # mediabox: (lower_left_x, lower_left_y, upper_right_x, upper_right_y)
    pdf_width_pt = mediabox.upper_right[0] - mediabox.lower_left[0]
    pdf_height_pt = mediabox.upper_right[1] - mediabox.lower_left[1]

    target_width_pt = width_mm * mm
    target_height_pt = height_mm * mm

    # 如果PDF尺寸小于等于目标尺寸，不需要裁剪
    if pdf_width_pt <= target_width_pt and pdf_height_pt <= target_height_pt:
        return pdf_bytes

    add_log("ok", f"PDF裁剪: {pdf_width_pt/mm:.1f}×{pdf_height_pt/mm:.1f}mm → {width_mm}×{height_mm}mm")
    return crop_pdf_to_size(pdf_bytes, width_mm, height_mm)


def send_to_printer(pdf_bytes: bytes, printer_name: str, copies: int = 1):
    # 自动裁剪PDF到100x100mm（外箱标签尺寸）
    pdf_bytes = crop_pdf_to_size_if_needed(pdf_bytes, 100, 100)

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(pdf_bytes)
    tmp.close()
    sumatra = get_sumatra()
    if sumatra:
        cmd = [sumatra, "-print-to", printer_name,
               "-print-settings", f"{copies}x,fit", "-silent", tmp.name]
        add_log("ok", f"打印命令：{' '.join(cmd)}")
        subprocess.run(cmd, check=True, timeout=30)
    else:
        os.startfile(tmp.name, "print")
    def _cleanup():
        time.sleep(15)
        try: os.unlink(tmp.name)
        except: pass
    threading.Thread(target=_cleanup, daemon=True).start()


def generate_fnsku_pdf(fnsku: str, sku: str, msku_shipping: str) -> bytes:
    W, H = 40 * mm, 60 * mm
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    bc_io = BytesIO()
    barcode.get("code128", fnsku, writer=ImageWriter()).write(
        bc_io,
        options={"module_width": 0.38, "module_height": 12.0,
                 "font_size": 0, "quiet_zone": 2.0, "write_text": False}
    )
    bc_io.seek(0)
    img = Image.open(bc_io)
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    cropped = BytesIO()
    img.save(cropped, format="PNG")
    cropped.seek(0)
    mx = 2 * mm
    bh = 18 * mm
    by = H - 2 * mm - bh
    c.drawImage(ImageReader(cropped), x=mx, y=by, width=W-2*mx, height=bh, preserveAspectRatio=False)
    fy = by - 4.5 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(W/2, fy, fnsku)
    ly = fy - 2 * mm
    c.setLineWidth(0.6)
    c.line(mx, ly, W-mx, ly)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(W/2, ly-5.5*mm, sku)
    c.setFont("Helvetica", 8)
    c.drawCentredString(W/2, ly-10.5*mm, msku_shipping)
    c.save()
    return buf.getvalue()


def add_log(level: str, message: str):
    print_log.insert(0, {
        "time": datetime.now().strftime("%H:%M:%S"),
        "level": level,
        "message": message
    })
    if len(print_log) > 100:
        print_log.pop()


# ───────────────────────────────────────────────────────
# API（供 Ubuntu ERP 调用）
# ───────────────────────────────────────────────────────

@app.route("/ping")
def ping():
    return jsonify({"status": "ok", "printer": FNSKU_PRINTER, "sumatra": bool(get_sumatra())})


@app.route("/printers")
def list_printers():
    """列出 Windows 上所有已安装的打印机，用于确认打印机名称是否正确"""
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-Printer | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=10
        )
        names = [n.strip() for n in result.stdout.strip().splitlines() if n.strip()]
        matched_fnsku = FNSKU_PRINTER in names
        matched_box   = BOX_PRINTER in names
        return jsonify({
            "status": "ok",
            "installed_printers": names,
            "config": {
                "FNSKU_PRINTER": FNSKU_PRINTER,
                "FNSKU_PRINTER_found": matched_fnsku,
                "BOX_PRINTER": BOX_PRINTER,
                "BOX_PRINTER_found": matched_box,
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/logs")
def api_logs():
    return jsonify(print_log)

@app.route("/print/fnsku", methods=["POST"])
def api_fnsku():
    data = request.get_json()
    try:
        pdf = generate_fnsku_pdf(data["fnsku"], data["sku"], data["msku_shipping"])
        copies = int(data.get("copies", 1))
        send_to_printer(pdf, FNSKU_PRINTER, copies)
        add_log("ok", f"FNSKU {data['fnsku']} × {copies} 张")
        return jsonify({"status": "ok"})
    except Exception as e:
        add_log("err", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/print/fnsku/batch", methods=["POST"])
def api_fnsku_batch():
    items = request.get_json()
    if not isinstance(items, list):
        return jsonify({"status": "error", "message": "需要 JSON 数组"}), 400
    results, ok_count = [], 0
    for item in items:
        try:
            pdf = generate_fnsku_pdf(item["fnsku"], item["sku"], item["msku_shipping"])
            copies = int(item.get("copies", 1))
            send_to_printer(pdf, FNSKU_PRINTER, copies)
            results.append({"fnsku": item["fnsku"], "status": "ok"})
            ok_count += 1
        except Exception as e:
            results.append({"fnsku": item.get("fnsku","?"), "status": "error", "message": str(e)})
    add_log("ok", f"批量打印 {ok_count}/{len(items)} 条 FNSKU 标签")
    return jsonify({"status": "ok", "results": results})

@app.route("/print/box", methods=["POST"])
def api_box():
    try:
        pdf_bytes = request.data
        if not pdf_bytes:
            return jsonify({"status": "error", "message": "未收到 PDF 数据"}), 400
        copies = int(request.args.get("copies", 1))
        send_to_printer(pdf_bytes, BOX_PRINTER, copies)
        add_log("ok", f"外箱标签 × {copies} 张")
        return jsonify({"status": "ok"})
    except Exception as e:
        add_log("err", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500


# ───────────────────────────────────────────────────────
# 预览 API
# ───────────────────────────────────────────────────────

@app.route("/preview/fnsku", methods=["POST"])
def api_preview_fnsku():
    """FNSKU 预览 - 返回裁剪后的PDF base64"""
    data = request.get_json()
    try:
        pdf = generate_fnsku_pdf(data["fnsku"], data["sku"], data["msku_shipping"])
        # FNSKU是60x40mm，不需要裁剪，但为了统一处理也走裁剪流程
        pdf = crop_pdf_to_size_if_needed(pdf, 60, 40)
        return jsonify({"status": "ok", "pdf": base64.b64encode(pdf).decode("utf-8")})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/preview/box", methods=["POST"])
def api_preview_box():
    """外箱预览 - 返回裁剪后的PDF base64"""
    try:
        pdf_bytes = request.data
        if not pdf_bytes:
            return jsonify({"status": "error", "message": "未收到 PDF 数据"}), 400
        # 裁剪到100x100mm
        pdf = crop_pdf_to_size_if_needed(pdf_bytes, 100, 100)
        return jsonify({"status": "ok", "pdf": base64.b64encode(pdf).decode("utf-8")})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ───────────────────────────────────────────────────────
# Web 管理界面（内嵌 HTML）
# ───────────────────────────────────────────────────────

@app.route("/")
def index():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/html; charset=utf-8")


if __name__ == "__main__":
    print("=" * 52)
    print("  佳博打印代理服务")
    print("=" * 52)
    print(f"  管理界面：http://localhost:{PORT}")
    print(f"  FNSKU 打印机：{FNSKU_PRINTER}")
    sumatra = get_sumatra()
    print(f"  SumatraPDF：{'已找到' if sumatra else '未安装（建议安装，支持静默打印）'}")
    print("=" * 52)
    app.run(host="0.0.0.0", port=PORT, debug=False)

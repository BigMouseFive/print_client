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

import os, sys, json, tempfile, threading, subprocess, time
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
except ImportError as e:
    print(f"[错误] 缺少依赖，请运行：\n  pip install flask reportlab python-barcode[images] Pillow openpyxl\n{e}")
    sys.exit(1)

app = Flask(__name__)

# ═══════════════════════════════════════════════════════
# 配置 — 仅需修改这里
# ═══════════════════════════════════════════════════════
PORT          = 5050
FNSKU_PRINTER = "Gprinter GP-2120TU"   # 改为 Windows「设备和打印机」中的实际名称
BOX_PRINTER   = "Gprinter GP-2120TU"   # 外箱标签打印机（同一台则填一样）

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


def send_to_printer(pdf_bytes: bytes, printer_name: str, copies: int = 1):
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(pdf_bytes)
    tmp.close()
    sumatra = get_sumatra()
    if sumatra:
        cmd = [sumatra, "-print-to", printer_name,
               "-print-settings", f"{copies}x,fit", "-silent", tmp.name]
        subprocess.run(cmd, check=True, timeout=30)
    else:
        os.startfile(tmp.name, "print")
    def _cleanup():
        time.sleep(15)
        try: os.unlink(tmp.name)
        except: pass
    threading.Thread(target=_cleanup, daemon=True).start()


def generate_fnsku_pdf(fnsku: str, sku: str, msku_shipping: str) -> bytes:
    W, H = 60 * mm, 40 * mm
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
# Web 管理界面（内嵌 HTML）
# ───────────────────────────────────────────────────────

@app.route("/")
def index():
    return Response(HTML_PAGE, mimetype="text/html; charset=utf-8")


HTML_PAGE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>佳博打印服务</title>
<script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
<style>
:root{--bg:#f7f6f3;--surface:#fff;--border:rgba(0,0,0,.1);--border-md:rgba(0,0,0,.18);--text:#1a1a18;--muted:#6b6b67;--hint:#9b9b96;--blue:#1a56db;--blue-dk:#1245b0;--blue-lt:#ebf0ff;--green:#16a34a;--green-lt:#dcfce7;--red:#dc2626;--red-lt:#fee2e2;--amber:#d97706;--amber-lt:#fef3c7;--r:10px;--rsm:6px}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);font-size:14px;min-height:100vh}
.layout{display:flex;min-height:100vh}
.sidebar{width:220px;flex-shrink:0;background:var(--surface);border-right:0.5px solid var(--border);display:flex;flex-direction:column}
.sb-head{padding:20px 18px 16px;border-bottom:0.5px solid var(--border)}
.brand{display:flex;align-items:center;gap:10px}
.brand-icon{width:34px;height:34px;background:var(--blue);border-radius:8px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.brand-icon svg{width:18px;height:18px;fill:white}
.brand-name{font-size:15px;font-weight:600;line-height:1.2}
.brand-sub{font-size:11px;color:var(--muted)}
.nav{padding:10px;flex:1}
.nav-item{display:flex;align-items:center;gap:9px;padding:9px 10px;border-radius:var(--rsm);cursor:pointer;color:var(--muted);font-size:13.5px;border:none;background:none;width:100%;text-align:left;transition:background .12s,color .12s}
.nav-item svg{width:16px;height:16px;flex-shrink:0;opacity:.7}
.nav-item:hover{background:var(--bg);color:var(--text)}
.nav-item.active{background:var(--blue-lt);color:var(--blue);font-weight:500}
.nav-item.active svg{opacity:1}
.sb-foot{padding:14px 18px;border-top:0.5px solid var(--border)}
.status-pill{display:flex;align-items:center;gap:7px;padding:7px 10px;border-radius:var(--rsm);background:var(--bg);font-size:12px;color:var(--muted)}
.dot{width:7px;height:7px;border-radius:50%;background:#9ca3af;flex-shrink:0}
.dot.online{background:var(--green);box-shadow:0 0 0 2px var(--green-lt)}
.dot.offline{background:var(--red)}
.main{flex:1;overflow-y:auto}
.panel{display:none;padding:28px 32px;max-width:740px}
.panel.active{display:block}
.panel-title{font-size:19px;font-weight:600;margin-bottom:5px}
.panel-desc{font-size:13px;color:var(--muted);margin-bottom:22px}
.card{background:var(--surface);border:0.5px solid var(--border);border-radius:var(--r);padding:22px;margin-bottom:16px}
.fg{display:grid;gap:12px;margin-bottom:14px}
.fg.c2{grid-template-columns:1fr 1fr}
.fg.c1{grid-template-columns:1fr}
.field{display:flex;flex-direction:column;gap:5px}
.field label{font-size:12px;font-weight:500;color:var(--muted)}
.field input[type=text]{height:38px;border:0.5px solid var(--border-md);border-radius:var(--rsm);padding:0 11px;font-size:14px;color:var(--text);background:var(--surface);transition:border-color .15s,box-shadow .15s;outline:none}
.field input[type=text]:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(26,86,219,.12)}
.preview{background:var(--bg);border:0.5px solid var(--border);border-radius:var(--rsm);padding:13px 15px;margin-bottom:14px;min-height:76px}
.preview-hint{font-size:12px;color:var(--hint)}
.prow{display:flex;justify-content:space-between;font-size:13px;padding:2px 0}
.prow .k{color:var(--muted)}
.prow .v{font-weight:500;font-family:'Consolas',monospace}
.copies-bar{display:flex;align-items:center;gap:10px;margin-bottom:16px}
.copies-bar label{font-size:12px;font-weight:500;color:var(--muted)}
.qbtn{width:30px;height:30px;border:0.5px solid var(--border-md);border-radius:var(--rsm);background:var(--surface);cursor:pointer;font-size:17px;color:var(--text);display:flex;align-items:center;justify-content:center;transition:background .1s}
.qbtn:hover{background:var(--bg)}
.qnum{font-size:14px;font-weight:600;min-width:22px;text-align:center}
.btn{height:40px;border-radius:var(--rsm);font-size:14px;font-weight:500;cursor:pointer;padding:0 20px;border:none;transition:background .15s,transform .1s;display:inline-flex;align-items:center;justify-content:center;gap:7px}
.btn:active{transform:scale(.98)}
.btn-blue{background:var(--blue);color:white}
.btn-blue:hover{background:var(--blue-dk)}
.btn-blue:disabled{background:#c5c5c5;cursor:not-allowed;transform:none}
.btn-ghost{background:transparent;color:var(--text);border:0.5px solid var(--border-md)}
.btn-ghost:hover{background:var(--bg)}
.btn-full{width:100%}
.btn-sm{height:32px;font-size:13px;padding:0 14px}
.upload-zone{border:1.5px dashed var(--border-md);border-radius:var(--rsm);padding:20px;text-align:center;cursor:pointer;margin-bottom:12px;transition:border-color .15s,background .15s}
.upload-zone:hover{border-color:var(--blue);background:var(--blue-lt)}
.upload-zone.has-file{border-color:var(--green);background:var(--green-lt)}
.uz-icon{width:32px;height:32px;border-radius:7px;background:var(--blue-lt);display:inline-flex;align-items:center;justify-content:center;margin-bottom:7px}
.uz-icon.green{background:var(--green-lt)}
.uz-label{font-size:13px;color:var(--muted)}
.uz-hint{font-size:11px;color:var(--hint);margin-top:3px}
.toast-wrap{position:fixed;top:18px;right:18px;display:flex;flex-direction:column;gap:8px;z-index:999}
.toast{padding:11px 16px;border-radius:var(--rsm);font-size:13px;display:flex;align-items:center;gap:8px;max-width:320px;animation:slideIn .2s ease;box-shadow:0 2px 10px rgba(0,0,0,.08);border:0.5px solid}
.toast.ok{background:var(--green-lt);color:#14532d;border-color:#86efac}
.toast.err{background:var(--red-lt);color:#7f1d1d;border-color:#fca5a5}
@keyframes slideIn{from{opacity:0;transform:translateX(12px)}to{opacity:1;transform:none}}
.tbl-toolbar{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.tbl-toolbar .left{flex:1;display:flex;align-items:center;gap:8px}
.sel-info{font-size:13px;color:var(--muted)}
.tbl-wrap{border:0.5px solid var(--border);border-radius:var(--rsm);overflow:hidden;margin-bottom:12px}
table{width:100%;border-collapse:collapse;font-size:13px}
thead{background:var(--bg)}
th{padding:9px 12px;text-align:left;font-size:11.5px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;border-bottom:0.5px solid var(--border);white-space:nowrap}
td{padding:9px 12px;border-bottom:0.5px solid var(--border);color:var(--text);vertical-align:middle}
tr:last-child td{border-bottom:none}
tr.sel td{background:#eff6ff}
input[type=checkbox]{width:15px;height:15px;accent-color:var(--blue);cursor:pointer}
.qty-input{width:46px;height:28px;text-align:center;border:0.5px solid var(--border-md);border-radius:5px;font-size:13px;color:var(--text);background:var(--surface)}
.badge{font-size:11px;padding:2px 8px;border-radius:4px;font-weight:500;white-space:nowrap}
.bw{background:#f0f9ff;color:#0369a1}
.bd{background:var(--green-lt);color:#14532d}
.bf{background:var(--red-lt);color:#7f1d1d}
.br{background:var(--amber-lt);color:#92400e}
.prog-wrap{height:5px;background:var(--border);border-radius:3px;margin-bottom:12px;display:none;overflow:hidden}
.prog-fill{height:100%;background:var(--blue);border-radius:3px;width:0%;transition:width .35s ease}
.log-item{display:flex;gap:9px;align-items:flex-start;padding:7px 0;border-bottom:0.5px solid var(--border)}
.log-item:last-child{border-bottom:none}
.log-time{font-size:11px;font-family:'Consolas',monospace;color:var(--hint);flex-shrink:0;padding-top:2px}
.log-msg{font-size:13px;color:var(--muted);line-height:1.4}
.log-area{max-height:360px;overflow-y:auto}
.hint-box{background:var(--blue-lt);border:0.5px solid #bfdbfe;border-radius:var(--rsm);padding:10px 13px;font-size:12px;color:#1e40af;margin-bottom:14px;line-height:1.6}
.hint-box code{font-family:'Consolas',monospace;background:rgba(0,0,0,.07);padding:1px 5px;border-radius:3px}
</style>
</head>
<body>
<div class="toast-wrap" id="toasts"></div>
<div class="layout">
<div class="sidebar">
  <div class="sb-head">
    <div class="brand">
      <div class="brand-icon"><svg viewBox="0 0 24 24"><path d="M5 4h14a1 1 0 011 1v5H4V5a1 1 0 011-1zm-1 8h16v7a1 1 0 01-1 1H6a1 1 0 01-1-1v-7zm10 2v2h2v-2h-2z"/></svg></div>
      <div><div class="brand-name">打印服务</div><div class="brand-sub">佳博 · 本地代理</div></div>
    </div>
  </div>
  <nav class="nav">
    <button class="nav-item active" onclick="sw('fnsku',this)">
      <svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 5a2 2 0 012-2h14a2 2 0 012 2v3H3V5zm0 5h18v9a2 2 0 01-2 2H5a2 2 0 01-2-2v-9zm5 3v2h2v-2H8zm4 0v2h2v-2h-2z"/></svg>
      FNSKU 单张
    </button>
    <button class="nav-item" onclick="sw('batch',this)">
      <svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 5h16v2H4V5zm0 4h16v2H4V9zm0 4h10v2H4v-2zm0 4h7v2H4v-2z"/></svg>
      批量打印
    </button>
    <button class="nav-item" onclick="sw('box',this)">
      <svg viewBox="0 0 24 24" fill="currentColor"><path d="M20 7H4a2 2 0 00-2 2v10a2 2 0 002 2h16a2 2 0 002-2V9a2 2 0 00-2-2zm-9 9H5v-2h6v2zm8 0h-6v-2h6v2zM3 7l2-4h14l2 4H3z"/></svg>
      外箱标签
    </button>
    <button class="nav-item" onclick="sw('log',this)">
      <svg viewBox="0 0 24 24" fill="currentColor"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 7h6m-6 4h4"/></svg>
      打印记录
    </button>
  </nav>
  <div class="sb-foot">
    <div class="status-pill"><span class="dot" id="sdot"></span><span id="stxt" style="font-size:12px">检测中…</span></div>
  </div>
</div>
<div class="main">

  <div class="panel active" id="panel-fnsku">
    <div class="panel-title">FNSKU 商品标签</div>
    <div class="panel-desc">手动填写字段，生成并打印单张 60×40mm 标签</div>
    <div class="card">
      <div class="fg c1"><div class="field"><label>FNSKU 编号</label><input type="text" id="f-fnsku" placeholder="如 X002JGSKY9" oninput="upv()"></div></div>
      <div class="fg c2">
        <div class="field"><label>SKU</label><input type="text" id="f-sku" placeholder="如 GS7978" oninput="upv()"></div>
        <div class="field"><label>MSKU + 运输方式</label><input type="text" id="f-msku" placeholder="如 FBA-*KSA9  HAI" oninput="upv()"></div>
      </div>
      <div class="preview" id="prev-box"><span class="preview-hint">填写字段后预览</span></div>
      <div class="copies-bar">
        <label>打印份数</label>
        <button class="qbtn" onclick="adj('q1',-1)">&#8722;</button>
        <span class="qnum" id="q1">1</span>
        <button class="qbtn" onclick="adj('q1',1)">+</button>
      </div>
      <button class="btn btn-blue btn-full" onclick="doFnsku(event)">打印 FNSKU 标签</button>
    </div>
  </div>

  <div class="panel" id="panel-batch">
    <div class="panel-title">批量打印</div>
    <div class="panel-desc">导入 Excel 或 CSV，多选后批量打印 FNSKU 标签</div>
    <div class="card">
      <div class="hint-box">文件需包含列：<code>fnsku</code>、<code>sku</code>、<code>msku_shipping</code>，可选列 <code>copies</code>（份数，默认1）</div>
      <div class="upload-zone" id="batch-zone" onclick="document.getElementById('batch-input').click()">
        <div class="uz-icon" id="batch-icon"><svg viewBox="0 0 24 24" fill="#1a56db"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg></div>
        <div class="uz-label" id="batch-fname">点击选择 Excel / CSV 文件</div>
        <div class="uz-hint">支持 .xlsx .xls .csv</div>
      </div>
      <input type="file" id="batch-input" accept=".csv,.xlsx,.xls" style="display:none" onchange="loadBatch(this)">
      <div id="batch-content" style="display:none">
        <div class="tbl-toolbar">
          <div class="left">
            <input type="checkbox" id="chk-all" onchange="selAll(this)">
            <span class="sel-info" id="sel-info">已选 0 / 0 条</span>
          </div>
          <button class="btn btn-ghost btn-sm" onclick="clearSel()">取消全选</button>
          <button class="btn btn-blue btn-sm" id="btn-batch" onclick="doBatch()" disabled>打印已选</button>
        </div>
        <div class="prog-wrap" id="prog-wrap"><div class="prog-fill" id="prog-fill"></div></div>
        <div class="tbl-wrap">
          <table>
            <thead><tr>
              <th style="width:32px"></th>
              <th>FNSKU</th><th>SKU</th><th>MSKU / 运输方式</th>
              <th style="width:64px">份数</th><th style="width:68px">状态</th>
            </tr></thead>
            <tbody id="batch-body"></tbody>
          </table>
        </div>
        <div style="display:flex;justify-content:flex-end">
          <button class="btn btn-ghost btn-sm" onclick="resetBatch()">重新导入</button>
        </div>
      </div>
    </div>
  </div>

  <div class="panel" id="panel-box">
    <div class="panel-title">外箱标签</div>
    <div class="panel-desc">上传从亚马逊 Seller Central 下载的 PDF，直接打印到 100×100mm 标签纸</div>
    <div class="card">
      <div class="upload-zone" id="box-zone" onclick="document.getElementById('pdf-input').click()">
        <div class="uz-icon" id="box-icon"><svg viewBox="0 0 24 24" fill="#1a56db"><path d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2zm5-16l5 5h-5V5z"/></svg></div>
        <div class="uz-label" id="box-fname">点击选择 PDF 文件</div>
        <div class="uz-hint">仅支持 .pdf</div>
      </div>
      <input type="file" id="pdf-input" accept=".pdf" style="display:none" onchange="onPdf(this)">
      <div class="copies-bar">
        <label>打印份数</label>
        <button class="qbtn" onclick="adj('q2',-1)">&#8722;</button>
        <span class="qnum" id="q2">1</span>
        <button class="qbtn" onclick="adj('q2',1)">+</button>
      </div>
      <button class="btn btn-blue btn-full" id="btn-box" onclick="doBox(event)" disabled>选择文件后打印</button>
    </div>
  </div>

  <div class="panel" id="panel-log">
    <div class="panel-title">打印记录</div>
    <div class="panel-desc">本次服务启动后的打印历史（最多100条）</div>
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
        <span style="font-size:13px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px">最近记录</span>
        <button class="btn btn-ghost btn-sm" onclick="clearLogUI()">清空显示</button>
      </div>
      <div class="log-area" id="log-area"><div style="font-size:13px;color:var(--hint);padding:8px 0">暂无记录</div></div>
    </div>
  </div>

</div>
</div>
<script>
let q1=1,q2=1,rows=[],pdfFile=null;
function sw(name,el){document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));document.getElementById('panel-'+name).classList.add('active');el.classList.add('active');if(name==='log')loadLog();}
function adj(id,d){if(id==='q1'){q1=Math.max(1,Math.min(99,q1+d));document.getElementById('q1').textContent=q1;}else{q2=Math.max(1,Math.min(99,q2+d));document.getElementById('q2').textContent=q2;}}
function upv(){const f=document.getElementById('f-fnsku').value.trim(),s=document.getElementById('f-sku').value.trim(),m=document.getElementById('f-msku').value.trim(),box=document.getElementById('prev-box');if(!f&&!s&&!m){box.innerHTML='<span class="preview-hint">填写字段后预览</span>';return;}box.innerHTML=`<div class="prow"><span class="k">FNSKU</span><span class="v">${f||'—'}</span></div><div class="prow"><span class="k">SKU</span><span class="v">${s||'—'}</span></div><div class="prow"><span class="k">MSKU / 运输</span><span class="v">${m||'—'}</span></div><div class="prow"><span class="k">份数</span><span class="v">${q1}</span></div>`;}
function toast(type,msg){const el=document.createElement('div');el.className='toast '+type;el.textContent=(type==='ok'?'✓  ':'✕  ')+msg;document.getElementById('toasts').appendChild(el);setTimeout(()=>el.remove(),3500);}
async function loadLog(){try{const res=await fetch('/logs');const data=await res.json();const area=document.getElementById('log-area');if(!data.length){area.innerHTML='<div style="font-size:13px;color:var(--hint);padding:8px 0">暂无记录</div>';return;}area.innerHTML=data.map(item=>`<div class="log-item"><span class="log-time">${item.time}</span><span class="badge ${item.level==='ok'?'bd':'bf'}">${item.level==='ok'?'成功':'失败'}</span><span class="log-msg">${item.message}</span></div>`).join('');}catch(e){}}
function clearLogUI(){document.getElementById('log-area').innerHTML='<div style="font-size:13px;color:var(--hint);padding:8px 0">已清空</div>';}
async function doFnsku(ev){const fnsku=document.getElementById('f-fnsku').value.trim(),sku=document.getElementById('f-sku').value.trim(),msku=document.getElementById('f-msku').value.trim();if(!fnsku||!sku||!msku){toast('err','请填写所有字段');return;}const btn=ev.target;btn.disabled=true;btn.textContent='发送中…';try{const res=await fetch('/print/fnsku',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fnsku,sku,msku_shipping:msku,copies:q1})});const data=await res.json();if(data.status==='ok')toast('ok',`已打印 ${q1} 张 FNSKU 标签`);else toast('err',data.message||'打印失败');}catch(e){toast('err','无法连接打印服务');}finally{btn.disabled=false;btn.textContent='打印 FNSKU 标签';}}
function onPdf(input){if(!input.files.length)return;pdfFile=input.files[0];document.getElementById('box-fname').textContent=pdfFile.name;document.getElementById('box-zone').classList.add('has-file');document.getElementById('box-icon').classList.add('green');document.getElementById('box-icon').innerHTML='<svg viewBox="0 0 24 24" fill="#16a34a"><path d="M5 13l4 4L19 7"/></svg>';document.getElementById('btn-box').disabled=false;document.getElementById('btn-box').textContent='打印外箱标签';}
async function doBox(ev){if(!pdfFile)return;const btn=ev.target;btn.disabled=true;btn.textContent='发送中…';try{const buf=await pdfFile.arrayBuffer();const res=await fetch(`/print/box?copies=${q2}`,{method:'POST',headers:{'Content-Type':'application/pdf'},body:buf});const data=await res.json();if(data.status==='ok')toast('ok',`外箱标签已打印 ${q2} 张`);else toast('err',data.message||'打印失败');}catch(e){toast('err','无法连接打印服务');}finally{btn.disabled=false;btn.textContent='打印外箱标签';}}
function loadBatch(input){if(!input.files.length)return;const file=input.files[0];document.getElementById('batch-fname').textContent=file.name;const reader=new FileReader();reader.onload=function(e){let data;if(file.name.toLowerCase().endsWith('.csv')){data=parseCSV(e.target.result);}else{const wb=XLSX.read(e.target.result,{type:'array'});const ws=wb.Sheets[wb.SheetNames[0]];data=XLSX.utils.sheet_to_json(ws,{defval:''});}rows=normalizeRows(data);if(!rows.length){toast('err','未找到有效数据，请检查列名');return;}renderBatch();document.getElementById('batch-content').style.display='block';document.getElementById('batch-zone').classList.add('has-file');toast('ok',`已导入 ${rows.length} 条数据`);};if(file.name.toLowerCase().endsWith('.csv'))reader.readAsText(file,'UTF-8');else reader.readAsArrayBuffer(file);}
function parseCSV(text){const lines=text.trim().split(/\r?\n/);if(lines.length<2)return[];const headers=lines[0].split(',').map(h=>h.trim().replace(/^"|"$/g,''));return lines.slice(1).map(line=>{const vals=line.split(',').map(v=>v.trim().replace(/^"|"$/g,''));const obj={};headers.forEach((h,i)=>obj[h]=vals[i]||'');return obj;}).filter(r=>Object.values(r).some(v=>v));}
function normalizeRows(data){const get=(r,names)=>{for(const n of names){const k=Object.keys(r).find(k=>k.toLowerCase().trim()===n);if(k&&r[k]!==undefined)return String(r[k]).trim();}return'';};return data.map((r,i)=>({id:i,fnsku:get(r,['fnsku','fnsku编号','fnsku号']),sku:get(r,['sku','sku编号']),msku_shipping:get(r,['msku_shipping','msku+运输方式','msku','shipping','运输方式']),copies:parseInt(get(r,['copies','份数','数量']))||1,status:'wait',checked:false})).filter(r=>r.fnsku);}
function sbadge(s){const m={wait:['bw','待打印'],done:['bd','已完成'],fail:['bf','失败'],running:['br','打印中']};const[cls,label]=m[s]||m.wait;return`<span class="badge ${cls}">${label}</span>`;}
function renderBatch(){const tbody=document.getElementById('batch-body');tbody.innerHTML='';rows.forEach(r=>{const tr=document.createElement('tr');if(r.checked)tr.classList.add('sel');tr.innerHTML=`<td><input type="checkbox" ${r.checked?'checked':''} onchange="toggleRow(${r.id},this)"></td><td style="font-family:'Consolas',monospace;font-size:12px">${r.fnsku}</td><td>${r.sku}</td><td style="font-size:12px;color:var(--muted)">${r.msku_shipping}</td><td><input type="number" class="qty-input" min="1" max="99" value="${r.copies}" onchange="rows[${r.id}].copies=Math.max(1,parseInt(this.value)||1)"></td><td>${sbadge(r.status)}</td>`;tbody.appendChild(tr);});updateSel();}
function toggleRow(id,cb){rows[id].checked=cb.checked;cb.closest('tr').classList.toggle('sel',cb.checked);updateSel();}
function selAll(cb){rows.forEach(r=>r.checked=cb.checked);renderBatch();document.getElementById('chk-all').checked=cb.checked;}
function clearSel(){rows.forEach(r=>r.checked=false);document.getElementById('chk-all').checked=false;renderBatch();}
function resetBatch(){rows=[];document.getElementById('batch-content').style.display='none';document.getElementById('batch-fname').textContent='点击选择 Excel / CSV 文件';document.getElementById('batch-input').value='';document.getElementById('batch-zone').classList.remove('has-file');}
function updateSel(){const sel=rows.filter(r=>r.checked).length;document.getElementById('sel-info').textContent=`已选 ${sel} / ${rows.length} 条`;const btn=document.getElementById('btn-batch');btn.disabled=sel===0;btn.textContent=sel>0?`打印已选 (${sel})`:'打印已选';}
async function doBatch(){const sel=rows.filter(r=>r.checked);if(!sel.length)return;const btn=document.getElementById('btn-batch');btn.disabled=true;const prog=document.getElementById('prog-wrap'),fill=document.getElementById('prog-fill');prog.style.display='block';fill.style.width='0%';for(let i=0;i<sel.length;i++){sel[i].status='running';renderBatch();try{const res=await fetch('/print/fnsku',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fnsku:sel[i].fnsku,sku:sel[i].sku,msku_shipping:sel[i].msku_shipping,copies:sel[i].copies})});const data=await res.json();sel[i].status=data.status==='ok'?'done':'fail';}catch(e){sel[i].status='fail';}fill.style.width=Math.round((i+1)/sel.length*100)+'%';renderBatch();}setTimeout(()=>{prog.style.display='none';fill.style.width='0%';},800);const doneCount=sel.filter(r=>r.status==='done').length;const total=sel.filter(r=>r.status==='done').reduce((a,r)=>a+r.copies,0);toast(doneCount===sel.length?'ok':'err',`批量完成 ${doneCount}/${sel.length} 条，共 ${total} 张`);btn.disabled=false;updateSel();}
async function checkStatus(){try{const res=await fetch('/ping',{signal:AbortSignal.timeout(2000)});await res.json();document.getElementById('sdot').className='dot online';document.getElementById('stxt').textContent='打印机在线';}catch(e){document.getElementById('sdot').className='dot offline';document.getElementById('stxt').textContent='服务离线';}}
checkStatus();setInterval(checkStatus,15000);
</script>
</body>
</html>"""


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

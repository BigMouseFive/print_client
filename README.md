# 佳博打印代理服务

亚马逊 FBA 卖家标签打印解决方案。ERP 运行在 Ubuntu，打印机接在 Windows，通过本地打印代理服务桥接两端，实现一键打印。

---

## 文件说明

| 文件 | 运行位置 | 说明 |
|------|----------|------|
| `windows_print_agent.py` | Windows（接打印机的电脑） | 打印代理服务，含 Web 管理界面 |
| `erp_client.py` | Ubuntu（ERP 服务器） | ERP 调用打印的客户端封装 |

---

## 系统架构

```
Ubuntu ERP (FastAPI)
       │
       │  HTTP POST（局域网）
       ▼
Windows 打印代理服务 :5050
       │
       │  USB
       ▼
  佳博打印机
```

---

## 支持的标签类型

**FNSKU 商品标签（60×40mm）**
- 自动生成 Code128 条形码
- 包含字段：FNSKU 编号 / SKU / MSKU + 运输方式

**外箱标签（100×100mm）**
- 直接打印亚马逊 Seller Central 下载的 PDF，不做任何修改

---

## 快速开始

### 第一步：Windows 端部署

**安装依赖**

```bash
pip install flask reportlab python-barcode[images] Pillow openpyxl pypdf
```

**安装 SumatraPDF（推荐，支持静默打印）**

下载地址：https://www.sumatrapdfreader.org

**修改配置**

打开 `windows_print_agent.py`，找到顶部配置区，修改打印机名称：

```python
FNSKU_PRINTER = "Gprinter GP-1326D"   # 改为实际名称
BOX_PRINTER   = "Gprinter GP-1326D"   # 如有两台分别填写
```

> 打印机名称可在 Windows「控制面板 → 设备和打印机」中查看，需完全一致。

**启动服务**

```bash
python windows_print_agent.py
```

启动成功后输出：

```
====================================================
  佳博打印代理服务
====================================================
  管理界面：http://localhost:5050
  FNSKU 打印机：Gprinter GP-1326D
  SumatraPDF：已找到
====================================================
```

浏览器访问 `http://localhost:5050` 即可使用 Web 管理界面。

---

### 第二步：Ubuntu ERP 端部署

**查看 Windows 电脑的局域网 IP**

在 Windows 电脑命令行运行：

```
ipconfig
```

找到「IPv4 地址」，通常为 `192.168.x.x`。

**修改配置**

打开 `erp_client.py`，修改第13行：

```python
PRINT_AGENT_URL = "http://192.168.1.100:5050"   # 改为实际 IP
```

**复制到 ERP 项目目录**

```bash
cp erp_client.py /path/to/your/erp/project/
```

**在 FastAPI 路由中集成**

```python
from print_client import print_fnsku_label, print_fnsku_batch, print_box_label
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

router = APIRouter(prefix="/api/labels", tags=["labels"])

class FnskuReq(BaseModel):
    fnsku: str
    sku: str
    msku_shipping: str
    copies: int = 1

@router.post("/fnsku")
def api_print_fnsku(req: FnskuReq):
    try:
        print_fnsku_label(req.fnsku, req.sku, req.msku_shipping, req.copies)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/fnsku/batch")
def api_print_fnsku_batch(items: list[FnskuReq]):
    try:
        results = print_fnsku_batch([i.dict() for i in items])
        return {"status": "ok", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/box")
async def api_print_box(file: UploadFile = File(...), copies: int = 1):
    import tempfile, os
    content = await file.read()
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(content); tmp.close()
    try:
        print_box_label(tmp.name, copies)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp.name)
```

---

## Web 管理界面

服务启动后访问 `http://localhost:5050`，提供四个功能页：

| 页面 | 功能 |
|------|------|
| FNSKU 单张 | 手动填写字段，实时预览，单张打印 |
| 批量打印 | 导入 Excel / CSV，多选后批量打印，逐条显示进度和状态 |
| 外箱标签 | 上传亚马逊 PDF，直接打印 |
| 打印记录 | 查看本次启动后的打印历史 |

### 批量打印文件格式

Excel 或 CSV 文件需包含以下列（列名不区分大小写）：

| 列名 | 必填 | 说明 |
|------|------|------|
| `fnsku` | 是 | FNSKU 编号，如 `X002JGSKY9` |
| `sku` | 是 | SKU 编号，如 `GS7978` |
| `msku_shipping` | 是 | MSKU + 运输方式，如 `FBA-*KSA9  HAI` |
| `copies` | 否 | 打印份数，默认 1 |

CSV 示例：

```csv
fnsku,sku,msku_shipping,copies
X002JGSKY9,GS7978,FBA-*KSA9  HAI,2
X002ABCDEF,GS1234,FBA-*DXB5  SEA,1
X002GHIJKL,GS5678,FBA-*DXB5  AIR,3
```

---

## API 接口文档

所有接口由 `windows_print_agent.py` 提供，供 ERP 直接调用。

### GET /ping
检查服务状态。

```bash
curl http://192.168.1.100:5050/ping
```

返回：
```json
{"status": "ok", "printer": "Gprinter GP-1326D", "sumatra": true}
```

---

### POST /print/fnsku
打印单张 FNSKU 标签。

```bash
curl -X POST http://192.168.1.100:5050/print/fnsku \
  -H "Content-Type: application/json" \
  -d '{"fnsku":"X002JGSKY9","sku":"GS7978","msku_shipping":"FBA-*KSA9  HAI","copies":1}'
```

请求体：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `fnsku` | string | 是 | FNSKU 编号 |
| `sku` | string | 是 | SKU 编号 |
| `msku_shipping` | string | 是 | MSKU + 运输方式 |
| `copies` | int | 否 | 打印份数，默认 1 |

---

### POST /print/fnsku/batch
批量打印 FNSKU 标签，一次请求处理多条。

```bash
curl -X POST http://192.168.1.100:5050/print/fnsku/batch \
  -H "Content-Type: application/json" \
  -d '[
    {"fnsku":"X002JGSKY9","sku":"GS7978","msku_shipping":"FBA-*KSA9  HAI","copies":2},
    {"fnsku":"X002ABCDEF","sku":"GS1234","msku_shipping":"FBA-*DXB5  SEA","copies":1}
  ]'
```

返回：
```json
{
  "status": "ok",
  "results": [
    {"fnsku": "X002JGSKY9", "status": "ok"},
    {"fnsku": "X002ABCDEF", "status": "ok"}
  ]
}
```

---

### POST /print/box
打印外箱标签，请求体为 PDF 文件的二进制内容。

```bash
curl -X POST "http://192.168.1.100:5050/print/box?copies=1" \
  -H "Content-Type: application/pdf" \
  --data-binary @box_label.pdf
```

---

### GET /logs
获取打印日志（最近100条）。

```bash
curl http://192.168.1.100:5050/logs
```

---

## 开机自启（Windows）

新建 `start_print_agent.bat`，内容：

```bat
@echo off
cd /d C:\你的脚本目录
python windows_print_agent.py
```

按 `Win+R` 输入 `shell:startup`，将该 bat 文件放入打开的文件夹中即可。

---

## 开机自启（Linux systemd）

项目已提供一键安装脚本，支持将服务注册为 systemd 并设置开机自启。

**安装前提**
- 系统使用 systemd（大多数现代 Linux 发行版默认支持）
- 已安装 Python 3 及项目依赖：`pip install -r requirements.txt`

**一键安装**

```bash
chmod +x install_service.sh
./install_service.sh
```

脚本会自动：
1. 检测项目目录及 Python 环境
2. 生成 `print-client.service`
3. 注册到 systemd 并设置开机自启
4. 立即启动服务

**常用管理命令**

| 命令 | 说明 |
|------|------|
| `sudo systemctl status print-client` | 查看服务状态 |
| `sudo systemctl restart print-client` | 重启服务 |
| `sudo systemctl stop print-client` | 停止服务 |
| `sudo journalctl -u print-client -f` | 实时查看日志 |

**脚本其他用法**

```bash
./install_service.sh --status    # 查看服务状态
./install_service.sh --logs      # 查看实时日志
./install_service.sh --uninstall # 卸载服务
```

---

## 常见问题

**打印出来尺寸不对**

需在 Windows「设备和打印机 → 打印机属性 → 高级 → 新建纸张尺寸」中手动添加：
- FNSKU 标签：60mm × 40mm
- 外箱标签：100mm × 100mm

添加后在打印机首选项中将默认纸张设为对应尺寸。

**提示「SumatraPDF 未安装」**

服务仍可运行，但会调用系统默认 PDF 程序打印，可能短暂弹出窗口。建议安装 SumatraPDF 以支持完全静默打印：https://www.sumatrapdfreader.org

**ERP 报「无法连接打印代理」**

按顺序排查：
1. Windows 打印服务是否已启动（命令行无报错输出）
2. Windows 防火墙是否放行了 5050 端口（控制面板 → Windows Defender 防火墙 → 高级设置 → 入站规则 → 新建规则 → 端口 5050）
3. `PRINT_AGENT_URL` 中的 IP 是否正确（用 `ipconfig` 重新确认）
4. Ubuntu 和 Windows 是否在同一局域网

**批量导入后显示「未找到有效数据」**

检查 CSV / Excel 的列名是否与要求一致，列名支持中英文：`fnsku`、`sku`、`msku_shipping`（或 `MSKU+运输方式`）、`copies`（或 `份数`）。

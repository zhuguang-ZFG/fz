"""按产品源码识别机型；缺文件或未知身份不得降级为无换纸。"""
from dataclasses import dataclass
from pathlib import Path
import os
import re

@dataclass(frozen=True)
class ProductProfile:
    sku: str
    flash_mode: str
    pin_contract: str

def identify_product(root: Path) -> ProductProfile:
    src = root / "Grbl_Esp32/src"
    machine_selector = (src / "Machine.h").read_text(encoding="utf-8")
    selected = re.findall(r'^\s*#\s*include\s+"(Machines/[^"]+)"', machine_selector, re.M)
    if selected != ["Machines/custom_3axis_hr4988.h"]:
        raise ValueError("不支持的 Machine.h 选择，须显式增加机型契约")
    ini = (root / "platformio.ini").read_text(encoding="utf-8")
    active_ini = "\n".join(line.split(";", 1)[0] for line in ini.splitlines())
    flags = os.environ.get("PLATFORMIO_BUILD_FLAGS", "") + active_ini
    if "-DMACHINE_FILENAME" in flags:
        raise ValueError("MACHINE_FILENAME 覆盖使源码机型不确定，拒绝套用默认契约")
    mode = re.search(r'^\s*board_build.flash_mode\s*=\s*(\w+)\s*$', active_ini, re.M)
    if mode is None or mode.group(1) not in {"dio", "qio"}:
        raise ValueError("缺少明确的 flash_mode")
    header = (src / selected[0]).read_text(encoding="utf-8")
    # 去掉块/行注释后检查定义，不以目录名或缺失纸路文件作为免检依据。
    header = re.sub(r'/\*.*?\*/|//[^\n]*', '', header, flags=re.S)
    if re.search(r'^\s*#\s*define\s+GRBL_PAPER_SYSTEM\s+1\b', header, re.M):
        if '#define CUSTOM_CODE_FILENAME "Custom/paper_system.cpp"' not in header:
            raise ValueError("有换纸 SKU 的动作入口不匹配")
        return ProductProfile("paper", mode.group(1), "machine_pin_contract.json")
    if (re.search(r'^\s*#\s*define\s+GRBL_PAPER_SYSTEM\b', header, re.M)
            or '#define PAIXI_DEVICE_ID "PAIXI_WRITER_3AXIS"' not in header
            or '#define CUSTOM_CODE_FILENAME "Custom/paixi_writer_tool_change.cpp"' not in header):
        raise ValueError("既非已知有换纸机型，也非已核对的量产无换纸机型")
    identity = (src / "Grbl.h").read_text(encoding="utf-8")
    if not re.search(r'GRBL_VERSION_BUILD\s*=\s*"20260910"', identity):
        raise ValueError("量产版本戳与 S3 无换纸身份契约不一致")
    if mode.group(1) != "dio":
        raise ValueError("量产无换纸机型必须使用 DIO")
    return ProductProfile("nopaper", "dio", "machine_pin_contract_nopaper.json")

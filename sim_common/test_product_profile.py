"""机型不能由缺文件、目录名或错误固件身份推断；负例必须挡住免检。"""
from pathlib import Path
import tempfile
import unittest
from sim_common.product_profile import identify_product

class ProductProfileTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.src = self.root / "Grbl_Esp32/src"
        (self.src / "Machines").mkdir(parents=True)
        (self.src / "Machine.h").write_text('#include "Machines/custom_3axis_hr4988.h"')
        (self.src / "Grbl.h").write_text('const char* GRBL_VERSION_BUILD = "20260910";')
        (self.root / "platformio.ini").write_text('board_build.flash_mode = dio')
        self.header = self.src / "Machines/custom_3axis_hr4988.h"
        self.header.write_text('#define PAIXI_DEVICE_ID "PAIXI_WRITER_3AXIS"\n#define CUSTOM_CODE_FILENAME "Custom/paixi_writer_tool_change.cpp"')
    def test_nopaper_requires_known_identity_and_dio(self):
        self.assertEqual(identify_product(self.root).sku, "nopaper")
        (self.root / "platformio.ini").write_text('board_build.flash_mode = qio')
        with self.assertRaises(ValueError):
            identify_product(self.root)
    def test_missing_paper_header_is_not_nopaper(self):
        self.header.write_text('#define CUSTOM_CODE_FILENAME "Custom/paper_system.cpp"')
        with self.assertRaises(ValueError):
            identify_product(self.root)
    def test_paper_profile_keeps_paper_contract(self):
        self.header.write_text('#define GRBL_PAPER_SYSTEM 1\n#define CUSTOM_CODE_FILENAME "Custom/paper_system.cpp"')
        self.assertEqual(identify_product(self.root).pin_contract, "machine_pin_contract.json")
    def test_unknown_identity_and_machine_override_fail(self):
        (self.src / "Grbl.h").write_text('const char* GRBL_VERSION_BUILD = "wrong";')
        with self.assertRaises(ValueError):
            identify_product(self.root)
        (self.src / "Grbl.h").write_text('const char* GRBL_VERSION_BUILD = "20260910";')
        (self.root / "platformio.ini").write_text('board_build.flash_mode = dio\nbuild_flags = -DMACHINE_FILENAME=test.h')
        with self.assertRaises(ValueError):
            identify_product(self.root)

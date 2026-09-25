"""量产引脚契约及六类真实头文件缺陷注入。"""
from pathlib import Path
import tempfile
import unittest
from run_machine_pin_erc import load_contract, validate_contract
from run_machine_pin_mutation_campaign import run_campaign

class NopaperPinsTest(unittest.TestCase):
    def test_baseline_and_mutation_sensitivity(self):
        path = Path(__file__).with_name("machine_pin_contract_nopaper.json")
        contract = load_contract(path)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            header = root / contract["machine"]
            header.parent.mkdir(parents=True)
            pins = {"X_STEP_PIN": 27, "X_DIRECTION_PIN": 26, "Y_STEP_PIN": 33, "Y_DIRECTION_PIN": 32,
                    "Z_STEP_PIN": 14, "Z_DIRECTION_PIN": 12, "STEPPERS_DISABLE_PIN": 25}
            header.write_text("\n".join(f"#define {name} GPIO_NUM_{pin}" for name, pin in pins.items()))
            result = run_campaign(root, path)
            self.assertEqual(result["status"], "pass", result)
            self.assertEqual(result["mutation_score"], {"killed": 6, "total": 6})

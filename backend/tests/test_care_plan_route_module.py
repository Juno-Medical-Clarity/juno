import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
for path in (PROJECT_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class CarePlanRouteModuleTest(unittest.TestCase):
    def test_care_plan_route_module_exports_task_1_symbols(self):
        module_path = BACKEND_DIR / "routes" / "care_plan.py"
        spec = importlib.util.spec_from_file_location("care_plan_route_under_test", module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        self.assertEqual(module.care_plan_bp.name, "care_plan")
        self.assertTrue(callable(module.run_care_plan_pipeline))
        self.assertTrue(callable(module._care_plan_stream))
        self.assertTrue(callable(module.create_care_plan))
        self.assertNotIn("simplify_v1_2", vars(module))


if __name__ == "__main__":
    unittest.main()

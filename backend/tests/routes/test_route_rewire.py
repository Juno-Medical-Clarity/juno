import sys
import unittest
from pathlib import Path

from flask import Flask

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent
for path in (PROJECT_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class Task6RouteRewireTest(unittest.TestCase):
    def test_routes_package_registers_care_plan_blueprints_and_new_paths_only(self):
        import routes

        self.assertEqual(
            [bp.name for bp in routes.all_blueprints],
            ["care_plan", "saved_outputs", "datasets", "batch", "grading"],
        )

        app = Flask(__name__)
        for blueprint in routes.all_blueprints:
            app.register_blueprint(blueprint)

        rules = {rule.rule for rule in app.url_map.iter_rules()}
        expected_care_plan_rules = {
            "/care_plan",
            "/care_plan/saved",
            "/care_plan/saved/<doc_id>",
            "/care_plan/saved/<doc_id>/input-pdf-url",
            "/care_plan/datasets",
            "/care_plan/datasets/<group>/<input_id>/<string:filename>",
            "/care_plan/batch",
            "/care_plan/grade",
        }
        self.assertTrue(expected_care_plan_rules.issubset(rules))
        self.assertFalse(
            {
                "/simplify/saved",
                "/simplify/saved/<doc_id>",
                "/simplify/saved/<doc_id>/input-pdf-url",
                "/simplify/datasets",
                "/simplify/datasets/<group>/<input_id>/<string:filename>",
                "/simplify/batch",
                "/simplify/grade",
            }
            & rules
        )

    def test_batch_route_uses_care_plan_pipeline_and_save_helper_surface(self):
        from routes import batch

        self.assertIs(batch._pipeline_for_version("v1-2"), batch.run_care_plan_pipeline)
        with self.assertRaisesRegex(ValueError, "Unknown version 'v1-1'"):
            batch._pipeline_for_version("v1-1")
        self.assertTrue(callable(batch.save_care_plan_output))
        self.assertFalse(hasattr(batch, "save_simplify_output"))


if __name__ == "__main__":
    unittest.main()

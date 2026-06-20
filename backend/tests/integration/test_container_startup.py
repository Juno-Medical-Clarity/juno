import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


class ContainerStartupTest(unittest.TestCase):
    def test_app_imports_from_backend_workdir_layout(self):
        backend_dir = Path(__file__).resolve().parents[2]
        script = textwrap.dedent(
            """
            from unittest.mock import patch

            with patch("utils.firebase.initialize_firebase", return_value=None):
                import app  # noqa: F401
            """
        )
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=backend_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}",
        )

    def test_preflight_includes_cors_headers(self):
        backend_dir = Path(__file__).resolve().parents[2]
        script = textwrap.dedent(
            """
            from unittest.mock import patch

            with patch("utils.firebase.initialize_firebase", return_value=None):
                import app as app_module

            client = app_module.app.test_client()
            response = client.open(
                "/care_plan/datasets",
                method="OPTIONS",
                headers={
                    "Origin": "https://juno-medical-clarity.web.app",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "authorization,content-type,x-session-id",
                },
            )

            assert response.status_code == 200, response.status_code
            assert response.headers["Access-Control-Allow-Origin"] == "https://juno-medical-clarity.web.app"
            assert "authorization" in response.headers["Access-Control-Allow-Headers"]
            """
        )
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=backend_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()

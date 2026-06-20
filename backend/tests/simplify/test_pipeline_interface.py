from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_task5_removes_legacy_pipelines_and_renames_interface():
    assert not (BACKEND_DIR / "simplify" / "v1").exists()
    assert not (BACKEND_DIR / "simplify" / "v1_1").exists()
    assert (BACKEND_DIR / "simplify" / "v1_2").is_dir()

    interface_source = (BACKEND_DIR / "simplify" / "interface.py").read_text()
    assert "class CarePlanPipeline(ABC):" in interface_source
    assert "class SimplifyPipeline" not in interface_source
    assert "routes/care_plan.py" in interface_source
    assert "routes/simplify_v<X>.py" not in interface_source

    v1_2_source = (BACKEND_DIR / "simplify" / "v1_2" / "pipeline.py").read_text()
    assert "from simplify.interface import CarePlanPipeline" in v1_2_source
    assert "class V1_2Pipeline(CarePlanPipeline):" in v1_2_source
    assert "SimplifyPipeline" not in v1_2_source

import pytest
from flask import Flask


def test_routes_package_registers_care_plan_blueprints_and_new_paths_only():
    import routes

    assert [bp.name for bp in routes.all_blueprints] == [
        "care_plan", "batch", "care_plan_jobs", "batch_jobs", "saved_outputs", "datasets", "grading"
    ]

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
        "/care_plan/jobs",
        "/care_plan/batch/jobs",
    }
    assert expected_care_plan_rules.issubset(rules)
    assert not (
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


def test_batch_route_uses_care_plan_pipeline_and_save_helper_surface():
    from routes import batch

    assert batch._pipeline_for_version("v1-2") is batch.run_care_plan_pipeline
    with pytest.raises(ValueError, match="Unknown version 'v1-1'"):
        batch._pipeline_for_version("v1-1")
    assert callable(batch.save_care_plan_output)
    assert not hasattr(batch, "save_simplify_output")

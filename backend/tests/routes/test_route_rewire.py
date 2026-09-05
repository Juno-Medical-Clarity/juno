from flask import Flask


def test_routes_package_registers_care_plan_blueprints_and_new_paths_only():
    import routes

    assert [bp.name for bp in routes.API_BLUEPRINTS] == [
        "care_plan_jobs", "batch_jobs", "saved_outputs", "datasets",
        "clinician_dataset", "grading", "admin", "trial",
    ]

    app = Flask(__name__)
    for blueprint in routes.API_BLUEPRINTS:
        app.register_blueprint(blueprint)

    rules = {rule.rule for rule in app.url_map.iter_rules()}
    expected_care_plan_rules = {
        "/care_plan/saved",
        "/care_plan/saved/<doc_id>",
        "/care_plan/saved/<doc_id>/input-pdf-url",
        "/care_plan/datasets",
        "/care_plan/datasets/<group>/<input_id>/<string:filename>",
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

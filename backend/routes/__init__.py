from routes.care_plan import care_plan_bp
from routes.batch import batch_bp
from routes.saved_outputs import saved_outputs_bp
from routes.datasets import datasets_bp
from routes.grading import grading_bp
from routes.care_plan_jobs import care_plan_jobs_bp
from routes.batch_jobs import batch_jobs_bp
from routes.worker import worker_bp
from routes.admin import admin_bp

API_BLUEPRINTS = [
    care_plan_bp,
    batch_bp,
    care_plan_jobs_bp,
    batch_jobs_bp,
    saved_outputs_bp,
    datasets_bp,
    grading_bp,
    admin_bp,        # ← added; was only in ADMIN_BLUEPRINTS before
]

WORKER_BLUEPRINTS = [
    worker_bp,
]

ADMIN_BLUEPRINTS = [
    admin_bp,
]

all_blueprints = API_BLUEPRINTS

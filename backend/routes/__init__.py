from routes.saved_outputs import saved_outputs_bp
from routes.datasets import datasets_bp
from routes.clinician_dataset import clinician_dataset_bp
from routes.grading import grading_bp
from routes.care_plan_jobs import care_plan_jobs_bp
from routes.batch_jobs import batch_jobs_bp
from routes.worker import worker_bp
from routes.admin import admin_bp
from routes.trial import trial_bp

API_BLUEPRINTS = [
    care_plan_jobs_bp,
    batch_jobs_bp,
    saved_outputs_bp,
    datasets_bp,
    clinician_dataset_bp,
    grading_bp,
    admin_bp,
    trial_bp,
]

WORKER_BLUEPRINTS = [
    worker_bp,
]

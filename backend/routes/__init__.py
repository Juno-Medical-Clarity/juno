from routes.care_plan import care_plan_bp
from routes.saved_outputs import saved_outputs_bp
from routes.datasets import datasets_bp
from routes.batch import batch_bp
from routes.grading import grading_bp

all_blueprints = [care_plan_bp, saved_outputs_bp, datasets_bp, batch_bp, grading_bp]

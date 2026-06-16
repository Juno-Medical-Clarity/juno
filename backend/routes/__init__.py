from routes.simplify import simplify_bp
from routes.saved_outputs import saved_outputs_bp
from routes.datasets import datasets_bp
from routes.batch import batch_bp

all_blueprints = [simplify_bp, saved_outputs_bp, datasets_bp, batch_bp]

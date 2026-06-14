from routes.simplify import simplify_bp
from routes.simplify_v1_1 import simplify_v1_1_bp
from routes.simplify_v1_2 import simplify_v1_2_bp
from routes.saved_outputs import saved_outputs_bp

all_blueprints = [simplify_bp, simplify_v1_1_bp, simplify_v1_2_bp, saved_outputs_bp]

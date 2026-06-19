# WESAD Stress Detection Model Package

This folder is ready to copy into your VS Code project.

## Best model
DeepDNN

## Best threshold
0.8799999999999996

## Feature mode
wrist_chest

## Split mode
group_split

## Files
- inference.py: use this in your backend/project to load the model and predict.
- metadata.json: model information, threshold, labels, metrics.
- feature_names.json: expected feature names and order.
- sample_input.json: example input feature dictionary.
- models/: saved model files.
- requirements.txt: Python dependencies.
- example_predict.py: quick test script.
- model_selection_by_validation.csv: validation ranking.
- test_ranking_for_reporting.csv: test ranking.

## Setup in VS Code
pip install -r requirements.txt
python example_predict.py

## Usage
from inference import WESADStressPredictor
predictor = WESADStressPredictor("path/to/vscode_model_package")
result = predictor.predict_from_json("path/to/vscode_model_package/sample_input.json")
print(result)

## Important
The input must be extracted features, not raw sensor signals.

For bracelet-only deployment, retrain using:
FEATURE_MODE = "wrist"
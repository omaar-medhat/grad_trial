
from inference import WESADStressPredictor

predictor = WESADStressPredictor(".")

result = predictor.predict_from_json("sample_input.json")

print(result)

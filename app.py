import os
import json
import base64
import numpy as np
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from PIL import Image
import io
# Import the LiteRT Interpreter
from ai_edge_litert.interpreter import Interpreter

app = Flask(__name__)
CORS(app)

# --- Configuration ---
# Path to your assets folder (relative to app.py)
ASSETS_FOLDER = os.path.join(os.path.dirname(__file__), 'assets')

# Model input details (adjust based on your model's actual input)
IMG_HEIGHT = 256
IMG_WIDTH = 256
INPUT_SHAPE = (1, IMG_HEIGHT, IMG_WIDTH, 3) # (batch_size, height, width, channels)
INPUT_DTYPE = np.float32 # Common for normalized models

# --- Global variables for loaded assets ---
interpreter = None
labels = []
waste_guidelines = {}

def load_assets():
    """Loads the TFLite model, labels, and waste guidelines."""
    global interpreter, labels, waste_guidelines

    # Load TFLite model using LiteRTInterpreter
    model_path = os.path.join(ASSETS_FOLDER, 'model.tflite')
    if not os.path.exists(model_path):
        print(f"Error: Model file not found at: {model_path}")
        return False
    try:
        # Initialize LiteRT Interpreter
        interpreter = Interpreter(model_path)

        # Allocate tensors. The previous error indicated this step is necessary.
        interpreter.allocate_tensors()

        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()
        print(f"TFLite model loaded from: {model_path} using LiteRTInterpreter.")
        print("Model Input Details:", input_details)
        print("Model Output Details:", output_details)

        # Basic check for input shape consistency
        expected_input_shape = input_details[0]['shape']
        if not np.array_equal(expected_input_shape, INPUT_SHAPE):
            print(f"Warning: Model input shape {expected_input_shape} does not match expected {INPUT_SHAPE}. "
                  "This might lead to errors or incorrect predictions if not handled by model itself.")

    except Exception as e:
        print(f"Error loading TFLite model with LiteRTInterpreter: {e}")
        return False

    # Load labels
    labels_path = os.path.join(ASSETS_FOLDER, 'labels.txt')
    if os.path.exists(labels_path):
        with open(labels_path, 'r', encoding='utf-8') as f:
            labels = [line.strip() for line in f if line.strip()]
        print(f"Labels loaded from: {labels_path}")
    else:
        print(f"Warning: Labels file not found at: {labels_path}. Predictions will return raw indices.")

    # Load waste guidelines
    guidelines_path = os.path.join(ASSETS_FOLDER, 'waste_guidelines.json')
    if os.path.exists(guidelines_path):
        try:
            with open(guidelines_path, 'r', encoding='utf-8') as f:
                waste_guidelines = json.load(f)
            print(f"Waste guidelines loaded from: {guidelines_path}")
        except json.JSONDecodeError as e:
            print(f"Error decoding waste_guidelines.json: {e}")
        except Exception as e:
            print(f"Error loading waste_guidelines.json: {e}")
    else:
        print(f"Waste guidelines file not found at: {guidelines_path}. Continuing without it.")
    
    return True

# Load assets when the app starts
if not load_assets():
    print("Failed to load all necessary assets. The application may not function correctly.")

# --- Prediction Function ---
def predict_image(image_data_base64):
    """
    Performs image classification using the loaded LiteRTInterpreter model.
    Args:
        image_data_base64 (str): Base64 encoded image data.
    Returns:
        tuple: A tuple containing (response_data_dict, status_code).
    """
    if interpreter is None:
        return {"error": "AI model not loaded. Please check server logs."}, 500

    try:
        # Decode base64 image
        image_bytes = base64.b64decode(image_data_base64)
        image = Image.open(io.BytesIO(image_bytes)).convert('RGB')

        # Preprocess image
        image = image.resize((IMG_WIDTH, IMG_HEIGHT))
        image_array = np.asarray(image, dtype=INPUT_DTYPE)
        image_array = np.expand_dims(image_array, axis=0) # Add batch dimension

        # Normalize if your model expects normalized input (e.g., 0-1 or -1 to 1)
        image_array = image_array / 255.0 # Example for 0-1 normalization

        # Get input and output details from the interpreter
        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()

        # LiteRTInterpreter uses set_tensor to set input data
        interpreter.set_tensor(input_details[0]['index'], image_array)

        # Run inference
        interpreter.invoke()

        # LiteRTInterpreter uses get_tensor to retrieve output data
        output_data = interpreter.get_tensor(output_details[0]['index'])
        
        # Post-process output (e.g., softmax for classification)
        # If your model's last layer is already softmax, you might skip this.
        # For manual softmax:
        exp_output = np.exp(output_data[0] - np.max(output_data[0])) # Subtract max for numerical stability
        probabilities = exp_output / np.sum(exp_output)
        
        predicted_index = np.argmax(probabilities)
        confidence = float(probabilities[predicted_index])

        predicted_label = labels[predicted_index] if predicted_index < len(labels) else f"Unknown ({predicted_index})"

        # Get guidelines
        guideline_info = waste_guidelines.get(predicted_label, {
            "category": "Uncategorized",
            "instructions": "No specific instructions available.",
            "bin_color": "grey"
        })

        response_data = {
            "predicted_label": predicted_label,
            "confidence": confidence,
            "category": guideline_info["category"],
            "instructions": guideline_info["instructions"],
            "bin_color": guideline_info["bin_color"]
        }
        return response_data, 200

    except Exception as e:
        print(f"Prediction error: {e}")
        return {"error": f"Failed to process image or predict: {e}"}, 500

# --- Flask Routes ---

@app.route('/')
def index():
    """Root route, redirects to the prediction interface."""
    return render_template('home.html')

@app.route('/predict', methods=['GET', 'POST'])
def predict():
    """
    Handles GET requests to serve the HTML prediction page
    and POST requests for image classification.
    """
    if request.method == 'GET':
        # Serve the HTML page for image upload
        return render_template('predict.html')
    elif request.method == 'POST':
        # Handle the image prediction request
        data = request.get_json()
        if not data or 'image' not in data:
            return jsonify({"error": "No image data provided in JSON."}), 400

        image_data_base64 = data['image']
        response, status_code = predict_image(image_data_base64)
        return jsonify(response), status_code

if __name__ == '__main__':
    # Ensure the assets folder exists
    if not os.path.exists(ASSETS_FOLDER):
        os.makedirs(ASSETS_FOLDER)
        print(f"Created assets folder: {ASSETS_FOLDER}")
    
    app.run(host='0.0.0.0', port=5000, debug=True)


# import os
# import json
# import base64
# import numpy as np
# from flask import Flask, request, jsonify, render_template # Added render_template
# from flask_cors import CORS
# from PIL import Image
# import io
# import tensorflow as tf # Or tflite_runtime as tf

# app = Flask(__name__)
# CORS(app) # Enable CORS for all routes (still good practice even with same-origin requests)

# # --- Configuration ---
# # Path to your assets folder (relative to app.py)
# ASSETS_FOLDER = os.path.join(os.path.dirname(__file__), 'assets')

# # Model input details (adjust based on your model)
# IMG_HEIGHT = 256
# IMG_WIDTH = 256
# INPUT_SHAPE = (1, IMG_HEIGHT, IMG_WIDTH, 3) # (batch_size, height, width, channels)
# INPUT_DTYPE = np.float32 # Common for normalized models

# # --- Load Model and Labels ---
# interpreter = None
# labels = []
# waste_guidelines = {}

# def load_assets():
#     global interpreter, labels, waste_guidelines

#     # Load TFLite model
#     model_path = os.path.join(ASSETS_FOLDER, 'model.tflite')
#     if not os.path.exists(model_path):
#         print(f"Error: Model file not found at: {model_path}")
#         return False
#     try:
#         interpreter = tf.lite.Interpreter(model_path=model_path)
#         interpreter.allocate_tensors()
#         print(f"TFLite model loaded from: {model_path}")

#         # Get input and output details
#         input_details = interpreter.get_input_details()
#         output_details = interpreter.get_output_details()
#         print("Model Input Details:", input_details)
#         print("Model Output Details:", output_details)

#         # Basic check for input shape consistency (optional, but good for debugging)
#         expected_input_shape = input_details[0]['shape']
#         if not np.array_equal(expected_input_shape, INPUT_SHAPE):
#             print(f"Warning: Model input shape {expected_input_shape} does not match expected {INPUT_SHAPE}")

#     except Exception as e:
#         print(f"Error loading TFLite model: {e}")
#         return False

#     # Load labels
#     labels_path = os.path.join(ASSETS_FOLDER, 'labels.txt')
#     if os.path.exists(labels_path):
#         with open(labels_path, 'r', encoding='utf-8') as f:
#             labels = [line.strip() for line in f if line.strip()]
#         print(f"Labels loaded from: {labels_path}")
#     else:
#         print(f"Warning: Labels file not found at: {labels_path}. Predictions will return raw indices.")

#     # Load waste guidelines
#     guidelines_path = os.path.join(ASSETS_FOLDER, 'waste_guidelines.json')
#     if os.path.exists(guidelines_path):
#         try:
#             with open(guidelines_path, 'r', encoding='utf-8') as f:
#                 waste_guidelines = json.load(f)
#             print(f"Waste guidelines loaded from: {guidelines_path}")
#         except json.JSONDecodeError as e:
#             print(f"Error decoding waste_guidelines.json: {e}")
#         except Exception as e:
#             print(f"Error loading waste_guidelines.json: {e}")
#     else:
#         print(f"Waste guidelines file not found at: {guidelines_path}. Continuing without it.")
    
#     return True

# # Load assets when the app starts
# if not load_assets():
#     print("Failed to load all necessary assets. The application may not function correctly.")

# # --- Prediction Function ---
# def predict_image(image_data_base64):
#     if interpreter is None:
#         return {"error": "AI model not loaded. Please check server logs."}, 500

#     try:
#         # Decode base64 image
#         image_bytes = base64.b64decode(image_data_base64)
#         image = Image.open(io.BytesIO(image_bytes)).convert('RGB')

#         # Preprocess image
#         image = image.resize((IMG_WIDTH, IMG_HEIGHT))
#         image_array = np.asarray(image, dtype=INPUT_DTYPE)
#         image_array = np.expand_dims(image_array, axis=0) # Add batch dimension

#         # Normalize if your model expects normalized input (e.g., 0-1 or -1 to 1)
#         # This depends on how your model was trained. Common for TFLite models.
#         # Example for 0-1 normalization:
#         image_array = image_array / 255.0

#         # Get input and output details
#         input_details = interpreter.get_input_details()
#         output_details = interpreter.get_output_details()

#         # Set the tensor
#         interpreter.set_tensor(input_details[0]['index'], image_array)

#         # Run inference
#         interpreter.invoke()

#         # Get the output tensor
#         output_data = interpreter.get_tensor(output_details[0]['index'])
        
#         # Post-process output (e.g., softmax for classification)
#         # Assuming classification output is logits or probabilities
#         probabilities = tf.nn.softmax(output_data).numpy()[0] # Convert logits to probabilities if needed
        
#         predicted_index = np.argmax(probabilities)
#         confidence = float(probabilities[predicted_index])

#         predicted_label = labels[predicted_index] if predicted_index < len(labels) else f"Unknown ({predicted_index})"

#         # Get guidelines
#         guideline_info = waste_guidelines.get(predicted_label, {
#             "category": "Uncategorized",
#             "instructions": "No specific instructions available.",
#             "bin_color": "grey"
#         })

#         response_data = {
#             "predicted_label": predicted_label,
#             "confidence": confidence,
#             "category": guideline_info["category"],
#             "instructions": guideline_info["instructions"],
#             "bin_color": guideline_info["bin_color"]
#         }
#         return response_data, 200

#     except Exception as e:
#         print(f"Prediction error: {e}")
#         return {"error": f"Failed to process image or predict: {e}"}, 500

# # --- Flask Routes ---

# @app.route('/')
# def index():
#     return render_template('home.html')
#     # return "Welcome to the Waste Sorting Assistant API. Go to /predict to use the web interface."

# @app.route('/predict', methods=['GET', 'POST'])
# def predict():
#     if request.method == 'GET':
#         # Serve the HTML page for image upload
#         return render_template('predict.html')
#     elif request.method == 'POST':
#         # Handle the image prediction request
#         data = request.get_json()
#         if not data or 'image' not in data:
#             return jsonify({"error": "No image data provided in JSON."}), 400

#         image_data_base64 = data['image']
#         response, status_code = predict_image(image_data_base64)
#         return jsonify(response), status_code

# if __name__ == '__main__':
#     # Ensure the assets folder exists
#     if not os.path.exists(ASSETS_FOLDER):
#         os.makedirs(ASSETS_FOLDER)
#         print(f"Created assets folder: {ASSETS_FOLDER}")
    
#     # You might want to place dummy model.tflite, labels.txt, waste_guidelines.json
#     # if they don't exist for initial testing.
#     # E.g., create a dummy labels.txt:
#     # with open(os.path.join(ASSETS_FOLDER, 'labels.txt'), 'w') as f:
#     #     f.write("Recyclable\nOrganic\nNon-Recyclable\n")

#     app.run(host='0.0.0.0', port=5000, debug=True)
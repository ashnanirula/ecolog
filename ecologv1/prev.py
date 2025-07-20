import os
import base64
import requests
from flask import Flask, request, render_template, jsonify
from dotenv import load_dotenv
from openai import OpenAI

# Load API keys
load_dotenv()
app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Gemini settings (still used for species identification only)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

def generate_dalle_image(prompt):
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="hd",
        n=1
    )
    return response.data[0].url

def call_gemini(parts):
    body = {"contents": [{"parts": parts}]}
    headers = {"Content-Type": "application/json"}
    response = requests.post(GEMINI_URL, json=body, headers=headers)
    return response.json()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
@app.route('/analyze', methods=['POST'])
def analyze():
    image = request.files['image']
    base64_image = base64.b64encode(image.read()).decode("utf-8")

    try:
        # Step 1: Identify species name only
        gemini_response = call_gemini([
            {
                "inlineData": {
                    "mimeType": "image/jpeg",
                    "data": base64_image
                }
            },
            {
                "text": "Identify the species in this photo. Respond with the name of the species, it's scientific name, and a brief description of the species. Respond in the following format: {species_name} {scientific_name} {description}."
            }
        ])
        species_name = gemini_response['candidates'][0]['content']['parts'][0]['text'].strip()

        # Step 2: Define clean prompts per style
        prompt = f"Japanese watercolor painting of {species_name}, soft and flowing brushstrokes, clean white background, no labels."

        # Step 3: Generate images
        image = [generate_dalle_image(prompt)]

        return jsonify({
            'output': f"Species identified: {species_name}",
            'illustrations': image
        })

    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)



from flask import Flask, request, jsonify
from flask_cors import CORS
import os, uuid, base64, json, requests
from dotenv import load_dotenv
from openai import OpenAI
from flask import render_template

app = Flask(__name__)
CORS(app)
load_dotenv()

# Setup
DATA_FILE = 'ecolog_data.json'
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"notebooks": [], "discoveries": []}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def generate_dalle_image(prompt):
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="hd",
        n=1
    )
    return response.data[0].url

def call_gemini(parts):
    headers = {"Content-Type": "application/json"}
    body = {"contents": [{"parts": parts}]}
    response = requests.post(GEMINI_URL, headers=headers, json=body)
    return response.json()

@app.route('/api/ai-identify', methods=['POST'])
def ai_identify():
    image = request.files['image']
    base64_image = base64.b64encode(image.read()).decode("utf-8")
    try:
        response = call_gemini([
            {
                "inlineData": {
                    "mimeType": "image/jpeg",
                    "data": base64_image
                }
            },
            {
                "text": "Identify the species. Respond with: {name} {scientific_name} {description}."
            }
        ])
        text = response['candidates'][0]['content']['parts'][0]['text']
        parts = text.split(' ', 2)
        name = parts[0]
        sci_name = parts[1]
        desc = parts[2] if len(parts) > 2 else ""

        prompt = f"Japanese watercolor painting of {name}, soft brushstrokes, white background"
        image_url = generate_dalle_image(prompt)

        return jsonify({
            "title": name,
            "scientific": sci_name,
            "description": desc,
            "tags": ["AI-generated"],
            "fun_fact": "This species is being studied for its ecological value.",
            "image_url": image_url
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/notebooks', methods=['GET'])
def get_notebooks():
    return jsonify(load_data()["notebooks"])

@app.route('/api/notebooks', methods=['POST'])
def create_notebook():
    data = load_data()
    notebook = {
        "id": str(uuid.uuid4()),
        "name": request.json["name"],
        "image": "",
        "entries": []
    }
    data["notebooks"].append(notebook)
    save_data(data)
    return jsonify(notebook), 201

@app.route('/api/notebooks/<notebook_id>/entries', methods=['POST'])
def add_entry(notebook_id):
    data = load_data()
    for nb in data["notebooks"]:
        if nb["id"] == notebook_id:
            entry = {
                "id": str(uuid.uuid4()),
                "title": request.json["title"],
                "scientific": request.json["scientific"],
                "tags": request.json["tags"],
                "description": request.json["description"],
                "fun_fact": request.json["fun_fact"],
                "notes": request.json["notes"],
                "author": request.json["author"],
                "image_url": request.json["image_url"]
            }
            nb["entries"].append(entry)
            save_data(data)
            return jsonify(entry), 201
    return jsonify({"error": "Notebook not found"}), 404

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)

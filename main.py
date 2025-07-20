import os
import base64
import requests
import json
import uuid
from datetime import datetime
from flask import Flask, request, render_template, jsonify, send_file, make_response
from dotenv import load_dotenv
from openai import OpenAI
from io import BytesIO
import zipfile
import urllib.request

# Load API keys
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your-secret-key-here")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Store analysis results temporarily (in production, use a database)
analysis_results = {}

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
def analyze():
    image = request.files['image']
    base64_image = base64.b64encode(image.read()).decode("utf-8")

    try:
        # Step 1: Identify species info
        gemini_response = call_gemini([
            {
                "inlineData": {
                    "mimeType": "image/jpeg",
                    "data": base64_image
                }
            },
            {
                "text": "Identify the species in this photo. Respond with the name of the species and store {species_name}, its scientific name and store {scientific_name}, and a brief description of the species {description}. Respond in the following format: {species_name}, {scientific_name}, {description}."
            }
        ])
        gemini_text = gemini_response['candidates'][0]['content']['parts'][0]['text'].strip()
        species_name, scientific_name, description = [s.strip() for s in gemini_text.split(", ", 2)]

        # Step 2: Generate one styled image
        prompt = f"Japanese watercolor painting of {species_name}, soft and flowing brushstrokes, clean white background, no labels."
        illustrations = [generate_dalle_image(prompt)]

        # Step 3: Format response
        formatted_html = f"""
            <h2>Species Name</h2>
            <p>{species_name}</p>
            <br>
            <h2>Scientific Name</h2>
            <p><em>{scientific_name}</em></p>
            <br>
            <h2>Description</h2>
            <p>{description}</p>
        """

                # Generate unique ID for this analysis
        analysis_id = str(uuid.uuid4())

        # Store analysis results for download
        analysis_results[analysis_id] = {
            'species_name': species_name,
            'scientific_name': scientific_name,
            'description': description,
            'illustrations': illustrations,
            'timestamp': datetime.now().isoformat(),
            'formatted_html': formatted_html
        }

        return jsonify({
            'output_html': formatted_html,
            'illustrations': illustrations,
            'analysis_id': analysis_id,
            'download_available': True
        })

    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/download/<analysis_id>')
def download_results(analysis_id):
    """Download analysis results as a ZIP file containing report and images"""

    if analysis_id not in analysis_results:
        return jsonify({'error': 'Analysis not found'}), 404

    try:
        result = analysis_results[analysis_id]

        # Create a BytesIO object to store the ZIP file
        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add species report as HTML file
            report_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EcoLog Species Report - {result['species_name']}</title>
    <style>
        body {{
            font-family: 'Arial', sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.6;
            color: #333;
        }}
        .header {{
            background: linear-gradient(135deg, #7C9565, #ABBF9A);
            color: white;
            padding: 30px;
            border-radius: 10px;
            text-align: center;
            margin-bottom: 30px;
        }}
        .header h1 {{
            margin: 0;
            font-size: 2.5em;
        }}
        .scientific-name {{
            font-style: italic;
            font-size: 1.2em;
            margin-top: 10px;
        }}
        .content {{
            background: #f9f9f9;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .section {{
            margin-bottom: 25px;
        }}
        .section h2 {{
            color: #4A5A3F;
            border-bottom: 2px solid #7C9565;
            padding-bottom: 5px;
        }}
        .timestamp {{
            text-align: center;
            color: #666;
            font-size: 0.9em;
            margin-top: 20px;
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            color: #7C9565;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{result['species_name']}</h1>
        <div class="scientific-name">{result['scientific_name']}</div>
    </div>

    <div class="content">
        <div class="section">
            <h2>Species Description</h2>
            <p>{result['description']}</p>
        </div>

        <div class="section">
            <h2>Analysis Details</h2>
            <p><strong>Common Name:</strong> {result['species_name']}</p>
            <p><strong>Scientific Name:</strong> <em>{result['scientific_name']}</em></p>
            <p><strong>Analysis Date:</strong> {datetime.fromisoformat(result['timestamp']).strftime('%B %d, %Y at %I:%M %p')}</p>
        </div>
    </div>

    <div class="timestamp">
        Generated by EcoLog - Nature Discovery App
    </div>

    <div class="footer">
        🌿 Discover. Document. Preserve. 🌿
    </div>
</body>
</html>
"""
            zip_file.writestr(f"{result['species_name']}_report.html", report_html)

            # Add JSON data file
            json_data = {
                'species_name': result['species_name'],
                'scientific_name': result['scientific_name'],
                'description': result['description'],
                'analysis_date': result['timestamp'],
                'generated_by': 'EcoLog Nature Discovery App'
            }
            zip_file.writestr(f"{result['species_name']}_data.json", json.dumps(json_data, indent=2))

            # Download and add AI generated images
            for i, img_url in enumerate(result['illustrations']):
                try:
                    with urllib.request.urlopen(img_url) as response:
                        img_data = response.read()
                        zip_file.writestr(f"{result['species_name']}_illustration_{i+1}.png", img_data)
                except Exception as img_error:
                    print(f"Error downloading image {i+1}: {img_error}")
                    # Add error note in ZIP
                    zip_file.writestr(f"image_{i+1}_download_error.txt",
                                    f"Failed to download image: {img_error}\nOriginal URL: {img_url}")

        zip_buffer.seek(0)

        # Create response
        response = make_response(zip_buffer.read())
        response.headers['Content-Type'] = 'application/zip'
        response.headers['Content-Disposition'] = f'attachment; filename="{result["species_name"]}_EcoLog_Analysis.zip"'

        return response

    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

@app.route('/download-json/<analysis_id>')
def download_json(analysis_id):
    """Download analysis results as JSON file"""

    if analysis_id not in analysis_results:
        return jsonify({'error': 'Analysis not found'}), 404

    try:
        result = analysis_results[analysis_id]

        json_data = {
            'species_name': result['species_name'],
            'scientific_name': result['scientific_name'],
            'description': result['description'],
            'illustrations': result['illustrations'],
            'analysis_date': result['timestamp'],
            'generated_by': 'EcoLog Nature Discovery App'
        }

        response = make_response(json.dumps(json_data, indent=2))
        response.headers['Content-Type'] = 'application/json'
        response.headers['Content-Disposition'] = f'attachment; filename="{result["species_name"]}_analysis.json"'

        return response

    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

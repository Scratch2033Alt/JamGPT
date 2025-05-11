import os
import json
import tempfile
import uuid
from flask import Flask, request, send_file, jsonify
from urllib.request import urlopen
from io import BytesIO
from zipfile import ZipFile
from PIL import Image
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=["https://turbowarp.org", "https://scratch.mit.edu"])
TEMP_FOLDER = tempfile.mkdtemp()  # Temporary folder for SVG files

def svg_to_base64(svg_string):
    """Converts an SVG string to a base64 encoded SVG data URL."""
    import base64
    svg_bytes = svg_string.encode('utf-8')
    base64_string = base64.b64encode(svg_bytes).decode('utf-8')
    return f"data:image/svg+xml;base64,{base64_string}"

def base64_svg_to_svg_file(base64_svg, filename):
    """Decodes a base64 SVG data URL and saves it to a file."""
    import base64
    header, encoded = base64_svg.split(",", 1)
    svg_bytes = base64.b64decode(encoded)
    filepath = os.path.join(TEMP_FOLDER, filename)
    with open(filepath, 'wb') as f:
        f.write(svg_bytes)
    return filepath

def download_favicon_as_svg(filename):
    """Downloads the Scratch favicon and saves it as an SVG file (as PNG with .svg extension)."""
    try:
        response = urlopen("https://scratch.mit.edu/favicon.ico")
        image_data = response.read()
        img = Image.open(BytesIO(image_data))
        filepath = os.path.join(TEMP_FOLDER, filename)
        img.save(filepath, "PNG")
        return filepath
    except Exception as e:
        print(f"Error downloading favicon: {e}")
        return None

@app.route('/assets/<filename>', methods=['POST', 'OPTIONS'], strict_slashes=False)
def handle_assets(filename):
    if request.method == 'POST':
        try:
            svg_element = request.data.decode('utf-8')
            base64_svg = svg_to_base64(svg_element)
            filepath = base64_svg_to_svg_file(base64_svg, filename)
            return jsonify({"status": "ok", "message": f"SVG saved to {filepath}"}), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    elif request.method == 'OPTIONS':
        response = app.response_class(status=204)
        response.headers.add('Access-Control-Allow-Origin', request.headers.get('Origin'))
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response
    return '', 405

# --- Project Upload Route ---
@app.route('/upload/<project_uid>', methods=['PUT', 'OPTIONS'], strict_slashes=False) # Added strict_slashes=False
def handle_project_upload(project_uid):
    if request.method == 'PUT':
        try:
            project_data = request.get_json()
            if not project_data:
                return jsonify({"status": "error", "message": "Invalid JSON payload"}), 404
            zip_filename = f"{project_uid}.sb3"
            upload_dir = os.path.join(app.root_path, 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            zip_filepath = os.path.join(upload_dir, zip_filename)
            svg_files_to_add = {}

            if 'assets' in project_data and isinstance(project_data['assets'], list):
                for asset in project_data['assets']:
                    if isinstance(asset, dict) and 'name' in asset and 'url' in asset:
                        asset_name = asset['name']
                        asset_url = asset['url']
                        if asset_url.startswith("data:image/svg+xml;base64,"):
                            filepath = base64_svg_to_svg_file(asset_url, asset_name)
                            svg_files_to_add[asset_name] = filepath
                        else:
                            temp_svg_path = os.path.join(TEMP_FOLDER, asset_name)
                            if os.path.exists(temp_svg_path):
                                svg_files_to_add[asset_name] = temp_svg_path
                            else:
                                print(f"Warning: Missing SVG file '{asset_name}'. Downloading favicon.")
                                favicon_path = download_favicon_as_svg(asset_name)
                                if favicon_path:
                                    svg_files_to_add[asset_name] = favicon_path

            with ZipFile(zip_filepath, 'w') as zipf:
                zipf.writestr("project.json", json.dumps(project_data))
                for name, path in svg_files_to_add.items():
                    zipf.write(path, os.path.join("assets", name))

            return jsonify({"status": "ok", "autosave-interval": "120", "projectId": project_uid}), 200

        except Exception as e:
            return jsonify({"status": "ok", "autosave-interval": "25", "message": str(e)}), 500
    elif request.method == 'OPTIONS':
        response = app.response_class(status=204)
        origin = request.headers.get('Origin')
        if origin in ["https://turbowarp.org", "https://scratch.mit.edu"]: # Be more specific if needed
             response.headers.add('Access-Control-Allow-Origin', origin)
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Allow-Methods', 'PUT, OPTIONS')
        # Expanded allowed headers. Customize this list based on actual headers sent by client.
        allowed_headers = "Content-Type, Authorization, X-Requested-With, X-Project-Id, X-Token" 
        response.headers.add('Access-Control-Allow-Headers', allowed_headers)
        return response
    # This line should ideally not be reached if PUT/OPTIONS is correctly routed and handled.
    return jsonify({"status": "error", "message": "Method Not Allowed by function logic"}), 405


# --- Project Download Route ---
@app.route('/download/<project_id>', methods=['GET', 'OPTIONS'])
def get_project(project_id):
    if request.method == 'GET':
        upload_dir = os.path.join(app.root_path, 'uploads')
        zip_filename = f"{project_id}.sb3"
        zip_filepath = os.path.join(upload_dir, zip_filename)
        if os.path.exists(zip_filepath):
            return send_file(zip_filepath, as_attachment=True, download_name=f"{project_id}.sb3")
        else:
            return jsonify({"status": "error", "message": "Project not found"}), 404
    elif request.method == 'OPTIONS':
        response = app.response_class(status=204)
        origin = request.headers.get('Origin')
        if origin in ["https://turbowarp.org", "https://scratch.mit.edu"]: # Be more specific if needed
            response.headers.add('Access-Control-Allow-Origin', origin)

        response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS, PUT')
        # Consistent and comprehensive headers
        response.headers.add('Access-Control-Allow-Headers', 'accept-language,x-project-id,x-requested-with,x-run-id,x-token,accept,accept-version,content-type,request-id,origin,x-api-version,x-request-id')
        response.headers.add('Accept-Ranges', 'bytes')
        response.headers.add('referrer-policy', 'no-referrer')
        response.headers.add('server', 'nginx') # Note: Flask dev server is not nginx
        response.headers.add('access-control-allow-credentials', 'true') # If you use credentials
        return response
    return jsonify({"status": "error", "message": "Method Not Allowed by function logic"}), 405

if __name__ == '__main__':
    # Ensure temporary SVG files are cleaned up if needed, though TEMP_FOLDER is session-based
    app.run(debug=True)
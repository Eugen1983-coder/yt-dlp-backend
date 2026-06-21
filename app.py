import os
import subprocess
import json
import threading
import uuid
import base64
import io
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

# Set environment variable for yt-dlp JS runtime
os.environ['YT_DLP_JS_RUNTIME'] = 'deno'

# Path to store decoded YouTube cookies inside container
DECODED_COOKIES_PATH = '/app/youtube_cookies.txt'

# Decode the base64-encoded cookie file from environment variable at startup
cookie_b64 = os.getenv('YOUTUBE_COOKIES_B64')
if cookie_b64:
    with open(DECODED_COOKIES_PATH, 'wb') as f:
        f.write(base64.b64decode(cookie_b64))
else:
    print("Warning: YOUTUBE_COOKIES_B64 environment variable is not set. Some features may not work.")

# Directory to save downloaded videos
DOWNLOAD_DIR = './downloads/'

# In-memory task storage for download status tracking
tasks = {}

def run_yt_dlp_info(url, cookies_path=DECODED_COOKIES_PATH, use_remote_components=True):
    """
    Run yt-dlp to extract video info as JSON.
    """
    cmd = ['yt-dlp', '--no-warnings']
    if use_remote_components:
        cmd += ['--remote-components', 'ejs:github']
    if cookies_path and os.path.exists(cookies_path):
        cmd += ['--cookies', cookies_path]
    cmd += ['-j', url]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return {'status': 'error', 'message': result.stderr.strip()}
        return {'status': 'success', 'info': json.loads(result.stdout)}
    except subprocess.TimeoutExpired:
        return {'status': 'error', 'message': 'Request timed out'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def download_worker(task_id, url, output_path, cookies_path, use_remote_components):
    """
    Background worker to download video using yt-dlp.
    """
    tasks[task_id]['status'] = 'downloading'
    if not os.path.exists(output_path):
        os.makedirs(output_path, exist_ok=True)

    cmd = ['yt-dlp', '--no-warnings']
    if use_remote_components:
        cmd += ['--remote-components', 'ejs:github']
    if cookies_path and os.path.exists(cookies_path):
        cmd += ['--cookies', cookies_path]
    cmd += [
        '-f', 'bestvideo+bestaudio/best',
        '-o', os.path.join(output_path, '%(title)s.%(ext)s'),
        url
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        tasks[task_id]['status'] = 'completed'
    else:
        tasks[task_id]['status'] = 'failed'
        tasks[task_id]['error'] = result.stderr

@app.route('/info', methods=['POST'])
def video_info():
    """
    Endpoint to get video info JSON.
    """
    data = request.get_json(force=True) or {}
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    use_remote_components = data.get('use_remote_components', True)
    response = run_yt_dlp_info(url, DECODED_COOKIES_PATH, use_remote_components)
    return jsonify(response), (200 if response['status'] == 'success' else 500)

@app.route('/download', methods=['POST'])
def download_video():
    """
    Endpoint to start video download in background.
    """
    data = request.get_json(force=True) or {}
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    use_remote_components = data.get('use_remote_components', True)
    task_id = str(uuid.uuid4())
    tasks[task_id] = {'status': 'queued', 'url': url}

    thread = threading.Thread(
        target=download_worker,
        args=(task_id, url, DOWNLOAD_DIR, DECODED_COOKIES_PATH, use_remote_components)
    )
    thread.start()

    return jsonify({'status': 'success', 'task_id': task_id})

@app.route('/status/<task_id>', methods=['GET'])
def get_status(task_id):
    """
    Endpoint to get download task status.
    """
    task = tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)

@app.route('/download_info', methods=['POST'])
def download_info():
    """
    Endpoint to download extracted video info JSON as a file.
    """
    data = request.get_json(force=True) or {}
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    info = run_yt_dlp_info(url, DECODED_COOKIES_PATH)
    if info['status'] != 'success':
        return jsonify(info), 500

    json_data = json.dumps(info['info'], indent=2)
    buffer = io.BytesIO()
    buffer.write(json_data.encode('utf-8'))
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name='video_info.json',
        mimetype='application/json'
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
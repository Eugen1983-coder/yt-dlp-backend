import os
import subprocess
import json
import threading
import uuid
from flask import Flask, request, jsonify

app = Flask(__name__)

# Environment configuration
os.environ['YT_DLP_JS_RUNTIME'] = 'deno'
DEFAULT_COOKIES_PATH = '/storage/emulated/0/Download/cookies.txt'
DOWNLOAD_DIR = './downloads/'

# Simple in-memory storage for download status
tasks = {}

def run_yt_dlp_info(url, cookies_path=DEFAULT_COOKIES_PATH, use_remote_components=True):
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
    data = request.get_json(force=True) or {}
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    cookies_path = data.get('cookies_path', DEFAULT_COOKIES_PATH)
    use_remote_components = data.get('use_remote_components', True)
    response = run_yt_dlp_info(url, cookies_path, use_remote_components)
    return jsonify(response), (200 if response['status'] == 'success' else 500)

@app.route('/download', methods=['POST'])
def download_video():
    data = request.get_json(force=True) or {}
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    cookies_path = data.get('cookies_path', DEFAULT_COOKIES_PATH)
    use_remote_components = data.get('use_remote_components', True)
    task_id = str(uuid.uuid4())
    tasks[task_id] = {'status': 'queued', 'url': url}
    thread = threading.Thread(
        target=download_worker,
        args=(task_id, url, DOWNLOAD_DIR, cookies_path, use_remote_components)
    )
    thread.start()
    return jsonify({'status': 'success', 'task_id': task_id})

@app.route('/status/<task_id>', methods=['GET'])
def get_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
import os
import subprocess
import json
import threading
import uuid
import base64
import io
import random
import requests
import logging
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

# Set environment variable for yt-dlp JS runtime
os.environ['YT_DLP_JS_RUNTIME'] = 'deno'

# Configure logging
logging.basicConfig(level=logging.DEBUG, filename='app.log', format='%(asctime)s %(levelname)s:%(message)s')

# Path to store decoded YouTube cookies inside container
DECODED_COOKIES_PATH = '/app/youtube_cookies.txt'

# Decode the base64-encoded cookie file from environment variable at startup
cookie_b64 = os.getenv('YOUTUBE_COOKIES_B64')
if cookie_b64:
    with open(DECODED_COOKIES_PATH, 'wb') as f:
        f.write(base64.b64decode(cookie_b64))
    app.logger.info("Decoded cookies saved successfully.")
else:
    app.logger.warning("YOUTUBE_COOKIES_B64 environment variable is not set. Some features may not work.")

# Directory to save downloaded videos
DOWNLOAD_DIR = './downloads/'

# In-memory task storage for download status tracking
tasks = {}

# List to hold working proxies
working_proxies = []

# Fetch free proxies from ProxyScrape
def fetch_proxies():
    url = 'https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all'
    try:
        response = requests.get(url, timeout=10)
        proxies = response.text.splitlines()
        app.logger.info(f"Fetched {len(proxies)} proxies from ProxyScrape.")
        return proxies
    except Exception as e:
        app.logger.error(f"Failed to fetch proxies: {e}")
        return []

# Test if a proxy is working by making a request to Google
def test_proxy(proxy):
    proxies = {
        'http': f'http://{proxy}',
        'https': f'http://{proxy}',
    }
    try:
        response = requests.get('https://www.google.com', proxies=proxies, timeout=5)
        if response.status_code == 200:
            app.logger.debug(f"Proxy {proxy} is working.")
            return True
    except Exception as e:
        app.logger.debug(f"Proxy {proxy} failed: {e}")
    return False

# Initialize proxies on startup
def initialize_proxies():
    global working_proxies
    proxies = fetch_proxies()
    working_proxies = []
    for proxy in proxies:
        if test_proxy(proxy):
            working_proxies.append(proxy)
    app.logger.info(f"{len(working_proxies)} proxies are working and ready for use.")

# Run yt-dlp to extract video info as JSON with optional proxy
def run_yt_dlp_info(url, cookies_path=DECODED_COOKIES_PATH, use_remote_components=True, proxy=None):
    cmd = ['yt-dlp', '--no-warnings', '-v']  # verbose logging
    if use_remote_components:
        cmd += ['--remote-components', 'ejs:github']
    if cookies_path and os.path.exists(cookies_path):
        cmd += ['--cookies', cookies_path]
    if proxy:
        cmd += ['--proxy', f'http://{proxy}']
    cmd += ['-j', url]

    app.logger.debug(f"Running yt-dlp info command: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            app.logger.error(f"yt-dlp info error: {result.stderr.strip()}")
            return {'status': 'error', 'message': result.stderr.strip()}
        return {'status': 'success', 'info': json.loads(result.stdout)}
    except subprocess.TimeoutExpired:
        app.logger.error("yt-dlp info request timed out")
        return {'status': 'error', 'message': 'Request timed out'}
    except Exception as e:
        app.logger.error(f"yt-dlp info exception: {e}")
        return {'status': 'error', 'message': str(e)}

# Background worker to download video using yt-dlp with optional proxy
def download_worker(task_id, url, output_path, cookies_path, use_remote_components, proxy=None):
    tasks[task_id]['status'] = 'downloading'
    if not os.path.exists(output_path):
        os.makedirs(output_path, exist_ok=True)

    cmd = ['yt-dlp', '--no-warnings', '-v']
    if use_remote_components:
        cmd += ['--remote-components', 'ejs:github']
    if cookies_path and os.path.exists(cookies_path):
        cmd += ['--cookies', cookies_path]
    if proxy:
        cmd += ['--proxy', f'http://{proxy}']
    cmd += [
        '-f', 'bestvideo+bestaudio/best',
        '-o', os.path.join(output_path, '%(title)s.%(ext)s'),
        url
    ]

    app.logger.debug(f"Running yt-dlp download command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        tasks[task_id]['status'] = 'completed'
        app.logger.info(f"Download completed for task {task_id}")
    else:
        tasks[task_id]['status'] = 'failed'
        tasks[task_id]['error'] = result.stderr
        app.logger.error(f"Download failed for task {task_id}: {result.stderr}")

# API endpoint to get video info JSON
@app.route('/info', methods=['POST'])
def video_info():
    data = request.get_json(force=True) or {}
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    use_remote_components = data.get('use_remote_components', True)
    proxy = data.get('proxy')

    # If no proxy provided, rotate from working proxies
    if not proxy and working_proxies:
        proxy = random.choice(working_proxies)

    response = run_yt_dlp_info(url, DECODED_COOKIES_PATH, use_remote_components, proxy)
    return jsonify(response), (200 if response['status'] == 'success' else 500)

# API endpoint to start video download in background
@app.route('/download', methods=['POST'])
def download_video():
    data = request.get_json(force=True) or {}
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    use_remote_components = data.get('use_remote_components', True)
    proxy = data.get('proxy')

    if not proxy and working_proxies:
        proxy = random.choice(working_proxies)

    task_id = str(uuid.uuid4())
    tasks[task_id] = {'status': 'queued', 'url': url}

    thread = threading.Thread(
        target=download_worker,
        args=(task_id, url, DOWNLOAD_DIR, DECODED_COOKIES_PATH, use_remote_components, proxy)
    )
    thread.start()

    return jsonify({'status': 'success', 'task_id': task_id})

# API endpoint to get download task status
@app.route('/status/<task_id>', methods=['GET'])
def get_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)

# API endpoint to download extracted video info JSON as a file
@app.route('/download_info', methods=['POST'])
def download_info():
    data = request.get_json(force=True) or {}
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    proxy = data.get('proxy')
    if not proxy and working_proxies:
        proxy = random.choice(working_proxies)

    info = run_yt_dlp_info(url, DECODED_COOKIES_PATH, proxy=proxy)
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
    # Initialize proxies on startup
    initialize_proxies()

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
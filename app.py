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
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, send_file, abort
import datetime

app = Flask(__name__)

# Set environment variable for yt-dlp JS runtime
os.environ['YT_DLP_JS_RUNTIME'] = 'deno'

# Configure logging to file and console
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.log')
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s:%(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
app.logger = logger

# Read the LOG_DOWNLOAD_TOKEN from environment variables (set by Render)
LOG_DOWNLOAD_TOKEN = os.getenv('LOG_DOWNLOAD_TOKEN')

# Path to store decoded YouTube cookies inside container
DECODED_COOKIES_PATH = '/app/youtube_cookies.txt'

# Decode the base64-encoded cookie file from environment variable at startup
cookie_b64 = os.getenv('YOUTUBE_COOKIES_B64')
if cookie_b64:
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(DECODED_COOKIES_PATH), exist_ok=True)
        with open(DECODED_COOKIES_PATH, 'wb') as f:
            f.write(base64.b64decode(cookie_b64))
        app.logger.info("Decoded cookies saved successfully.")
    except Exception as e:
        app.logger.error(f"Failed to decode and save cookies: {e}")
else:
    app.logger.warning("YOUTUBE_COOKIES_B64 environment variable is not set. Some features may not work.")

# Directory to save downloaded videos
DOWNLOAD_DIR = './downloads/'

# In-memory task storage for download status tracking
tasks = {}

# List to hold working proxies
working_proxies = []

# Proxy log file path inside project directory
PROXY_LOG_PATH = os.path.join(os.getcwd(), 'proxy.log')

# --- Proxy Testing and Logging ---

def log_proxy_result(proxy, success, error_msg=None):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status = 'SUCCESS' if success else 'FAILURE'
    log_line = f"{timestamp} - {proxy} - {status}"
    if error_msg:
        log_line += f" - {str(error_msg)[:50]}"
    with open(PROXY_LOG_PATH, 'a') as log_file:
        log_file.write(log_line + "\n")

def test_proxy(proxy):
    proxies = {
        'http': f'http://{proxy}',
        'https': f'http://{proxy}',
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get('https://www.youtube.com', proxies=proxies, headers=headers, timeout=10)
        if response.status_code == 200:
            log_proxy_result(proxy, True)
            app.logger.debug(f"Proxy {proxy} is working.")
            return True
        else:
            log_proxy_result(proxy, False, f"Status code: {response.status_code}")
    except Exception as e:
        log_proxy_result(proxy, False, e)
        app.logger.debug(f"Proxy {proxy} failed: {e}")
    return False

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

def initialize_proxies():
    global working_proxies
    proxies = fetch_proxies()
    working_proxies = []

    # Clear previous proxy log
    try:
        open(PROXY_LOG_PATH, 'w').close()
    except Exception as e:
        app.logger.error(f"Failed to clear proxy log: {e}")

    # Use ThreadPoolExecutor for faster proxy testing
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(test_proxy, proxies)
        for proxy, is_working in zip(proxies, results):
            if is_working:
                working_proxies.append(proxy)

    app.logger.info(f"{len(working_proxies)} proxies are working and ready for use.")
    app.logger.info(f"Proxy test log saved to: {PROXY_LOG_PATH}")

# --- yt-dlp Command Wrappers ---

def run_yt_dlp_info(url, cookies_path=DECODED_COOKIES_PATH, use_remote_components=True, proxy=None):
    cmd = ['yt-dlp', '--no-warnings', '-v']
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
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            tasks[task_id]['status'] = 'completed'
            app.logger.info(f"Download completed for task {task_id}")
        else:
            tasks[task_id]['status'] = 'failed'
            tasks[task_id]['error'] = result.stderr
            app.logger.error(f"Download failed for task {task_id}: {result.stderr}")
    except subprocess.TimeoutExpired:
        tasks[task_id]['status'] = 'failed'
        tasks[task_id]['error'] = 'Download timed out'
        app.logger.error(f"Download timed out for task {task_id}")
    except Exception as e:
        tasks[task_id]['status'] = 'failed'
        tasks[task_id]['error'] = str(e)
        app.logger.error(f"Download exception for task {task_id}: {e}")

# --- Flask API Endpoints ---

@app.route('/info', methods=['POST'])
def video_info():
    data = request.get_json(force=True) or {}
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    use_remote_components = data.get('use_remote_components', True)
    proxy = data.get('proxy')

    if not proxy and working_proxies:
        proxy = random.choice(working_proxies)

    response = run_yt_dlp_info(url, DECODED_COOKIES_PATH, use_remote_components, proxy)
    return jsonify(response), (200 if response['status'] == 'success' else 500)

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

@app.route('/status/<task_id>', methods=['GET'])
def get_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)

@app.route('/download_info', methods=['POST'])
def download_info():
    data = request.get_json(force=True) or {}
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    use_remote_components = data.get('use_remote_components', True)
    proxy = data.get('proxy')

    if not proxy and working_proxies:
        proxy = random.choice(working_proxies)

    info = run_yt_dlp_info(url, DECODED_COOKIES_PATH, use_remote_components, proxy)
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

# --- New endpoint for downloading app.log securely ---

@app.route('/download_log', methods=['GET'])
def download_log():
    # Simple token authentication via query parameter or header
    token = request.args.get('token') or request.headers.get('X-Log-Token')
    if not LOG_DOWNLOAD_TOKEN:
        app.logger.error("LOG_DOWNLOAD_TOKEN environment variable is not set.")
        abort(500, description="Server configuration error: LOG_DOWNLOAD_TOKEN not set")

    if token != LOG_DOWNLOAD_TOKEN:
        app.logger.warning(f"Unauthorized log download attempt with token: {token}")
        abort(403, description="Forbidden: Invalid or missing token")

    if not os.path.exists(LOG_FILE):
        app.logger.error("Log file not found for download")
        return jsonify({'error': 'Log file not found'}), 404

    try:
        return send_file(
            LOG_FILE,
            as_attachment=True,
            download_name='app.log',
            mimetype='text/plain'
        )
    except Exception as e:
        app.logger.error(f"Error sending log file: {e}")
        return jsonify({'error': 'Failed to send log file'}), 500

if __name__ == '__main__':
    initialize_proxies()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
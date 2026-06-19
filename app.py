import os
import subprocess
import json
from flask import Flask, request, jsonify
import threading

app = Flask(__name__)

# Set environment variable for yt-dlp JS runtime
os.environ['YT_DLP_JS_RUNTIME'] = 'deno'

# Path to your working cookies file (adjust if needed)
COOKIES_PATH = '/storage/emulated/0/Download/cookies.txt'

DOWNLOAD_DIR = './downloads/'


def run_yt_dlp_info(url):
    cmd = [
        'yt-dlp',
        '--remote-components', 'ejs:github',
        '--cookies', COOKIES_PATH,
        '-j',  # dump JSON info
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {'status': 'error', 'message': result.stderr}
    try:
        return {'status': 'success', 'info': json.loads(result.stdout)}
    except json.JSONDecodeError:
        return {'status': 'error', 'message': 'Failed to parse yt-dlp output'}


def download_in_background(url, output_path):
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    cmd = [
        'yt-dlp',
        '--remote-components', 'ejs:github',
        '--cookies', COOKIES_PATH,
        '-f', 'bestvideo+bestaudio/best',
        '-o', os.path.join(output_path, '%(title)s.%(ext)s'),
        url
    ]
    subprocess.run(cmd)


@app.route('/info', methods=['POST'])
def video_info():
    data = request.get_json(force=True)
    url = data.get('url')
    if not url:
        return jsonify({'status': 'error', 'message': 'No URL provided'}), 400

    response = run_yt_dlp_info(url)
    if response['status'] == 'error':
        return jsonify(response), 500
    return jsonify(response)


@app.route('/download', methods=['POST'])
def download_video():
    data = request.get_json(force=True)
    url = data.get('url')
    if not url:
        return jsonify({'status': 'error', 'message': 'No URL provided'}), 400

    threading.Thread(target=download_in_background, args=(url, DOWNLOAD_DIR)).start()
    return jsonify({'status': 'success', 'message': 'Download started in background'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
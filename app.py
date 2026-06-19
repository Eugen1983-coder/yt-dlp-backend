from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL
import threading
import os
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration constants
COOKIES_PATH = '/data/data/com.termux/files/home/yt-dlp-backend/cookies/cookies.txt'
DOWNLOAD_DIR = './downloads/'

def get_common_ydl_opts():
    opts = {
        'cookiefile': COOKIES_PATH,
        'quiet': True,
        'no_warnings': True,
    }
    if not os.path.exists(COOKIES_PATH):
        logger.warning(f"Cookie file not found at {COOKIES_PATH}, proceeding without cookies")
        del opts['cookiefile']
    return opts

@app.route('/info', methods=['POST'])
def video_info():
    data = request.get_json(force=True)
    url = data.get('url')
    if not url:
        return jsonify({'status': 'error', 'message': 'No URL provided'}), 400

    ydl_opts = {
        **get_common_ydl_opts(),
        'format': 'bestvideo+bestaudio/best',
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'allsubtitles': True,
        'noplaylist': True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            detailed_formats = []
            for f in info.get('formats', []):
                detailed_formats.append({
                    'format_id': f.get('format_id'),
                    'ext': f.get('ext'),
                    'resolution': f.get('resolution'),
                    'filesize': f.get('filesize') or f.get('filesize_approx'),
                    'vcodec': f.get('vcodec'),
                    'acodec': f.get('acodec'),
                    'url': f.get('url'),
                })

            response = {
                'id': info.get('id'),
                'title': info.get('title'),
                'uploader': info.get('uploader'),
                'duration': info.get('duration'),
                'thumbnail': info.get('thumbnail'),
                'description': (info.get('description') or '')[:500] + "...",
                'formats': detailed_formats,
                'subtitles': info.get('subtitles'),
                'chapters': info.get('chapters'),
            }

        return jsonify({'status': 'success', 'info': response})
    except Exception as e:
        logger.error(f"Error fetching info: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

def download_task(url, output_path):
    try:
        if not os.path.exists(output_path):
            os.makedirs(output_path)

        ydl_opts = {
            **get_common_ydl_opts(),
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
        }

        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        logger.info(f"Download completed for: {url}")
    except Exception as e:
        logger.error(f"Download failed for {url}: {str(e)}")

@app.route('/download', methods=['POST'])
def download_video():
    data = request.get_json(force=True)
    url = data.get('url')
    if not url:
        return jsonify({'status': 'error', 'message': 'No URL provided'}), 400

    threading.Thread(target=download_task, args=(url, DOWNLOAD_DIR)).start()

    return jsonify({
        'status': 'success',
        'message': 'Download started in background',
        'target_dir': DOWNLOAD_DIR
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
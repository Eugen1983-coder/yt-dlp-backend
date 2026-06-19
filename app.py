from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL
import threading

app = Flask(__name__)

@app.route('/info', methods=['POST'])
def video_info():
    data = request.get_json(force=True)
    url = data.get('url')
    if not url:
        return jsonify({'status': 'error', 'message': 'No URL provided'}), 400

    try:
        with YoutubeDL({}) as ydl:
            info = ydl.extract_info(url, download=False)
        return jsonify({'status': 'success', 'info': info})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def download_in_background(url, output_path):
    ydl_opts = {'outtmpl': output_path + '%(title)s.%(ext)s'}
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

@app.route('/download', methods=['POST'])
def download_video():
    data = request.get_json(force=True)
    url = data.get('url')
    if not url:
        return jsonify({'status': 'error', 'message': 'No URL provided'}), 400

    # Start download in a separate thread to avoid blocking
    threading.Thread(target=download_in_background, args=(url, './downloads/')).start()

    return jsonify({'status': 'success', 'message': 'Download started'})

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

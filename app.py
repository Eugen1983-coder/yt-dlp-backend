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

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',  # best video + audio or fallback best
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'allsubtitles': True,
        'forcejson': True,
        'simulate': True,
        'noplaylist': True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            # Extract detailed formats info
            formats = info.get('formats', [])
            detailed_formats = []
            for f in formats:
                detailed_formats.append({
                    'format_id': f.get('format_id'),
                    'ext': f.get('ext'),
                    'acodec': f.get('acodec'),
                    'vcodec': f.get('vcodec'),
                    'format_note': f.get('format_note'),
                    'fps': f.get('fps'),
                    'width': f.get('width'),
                    'height': f.get('height'),
                    'tbr': f.get('tbr'),  # total bitrate
                    'filesize': f.get('filesize'),
                    'url': f.get('url'),
                    'protocol': f.get('protocol'),
                    'quality': f.get('quality'),
                    'audio_channels': f.get('audio_channels'),
                    'language': f.get('language'),
                })

            # Prepare a cleaner response with key info
            response = {
                'id': info.get('id'),
                'title': info.get('title'),
                'uploader': info.get('uploader'),
                'duration': info.get('duration'),
                'view_count': info.get('view_count'),
                'like_count': info.get('like_count'),
                'dislike_count': info.get('dislike_count'),
                'description': info.get('description'),
                'thumbnail': info.get('thumbnail'),
                'webpage_url': info.get('webpage_url'),
                'formats': detailed_formats,
                'subtitles': info.get('subtitles'),
                'automatic_captions': info.get('automatic_captions'),
                'chapters': info.get('chapters'),
            }

        return jsonify({'status': 'success', 'info': response})
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

    threading.Thread(target=download_in_background, args=(url, './downloads/')).start()

    return jsonify({'status': 'success', 'message': 'Download started'})

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
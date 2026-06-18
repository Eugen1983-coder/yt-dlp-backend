from flask import Flask, request, jsonify
import yt_dlp
import traceback

app = Flask(__name__)

@app.route('/formats', methods=['POST'])
def formats():
    url = request.form.get('url')
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400

    ydl_opts = {
        'quiet': False,          # Show detailed logs for debugging
        'skip_download': True,   # Do not download video
        'cookiefile': None,      # Set if you handle cookies
    }

    try:
        yt_dlp_version = yt_dlp.__version__
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            return jsonify({
                'yt_dlp_version': yt_dlp_version,
                'formats_count': len(formats),
                'formats': formats,
            })
    except Exception as e:
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc(),
            'yt_dlp_version': yt_dlp.__version__,
        }), 500

if __name__ == '__main__':
    app.run(debug=True)
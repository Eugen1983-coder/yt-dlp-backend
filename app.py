from flask import Flask, request, jsonify
import yt_dlp
import os

app = Flask(__name__)

# Fixed path to your YouTube cookies file
FIXED_COOKIES_PATH = './cookies/cookies.txt'

@app.route('/extract', methods=['POST'])
def extract():
    url = request.form.get('url')
    cookies_file = request.files.get('cookies')

    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400

    # Set environment variable for JS runtime as 'deno'
    os.environ['YT_DLP_JS_RUNTIME'] = 'deno'

    ydl_opts = {
        'quiet': False,  # Set to False to see verbose output like -v
        'skip_download': True,
        'forcejson': True,
        'remote_components': ['ejs:github'],  # Equivalent to --remote-components ejs:github
        'cookiefile': None,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['en', 'ru'],
        'embedsubtitles': True,
        'format': 'best',  # You can adjust format selection as needed
    }

    # Handle cookies file: priority to uploaded file, else fixed path if exists
    if cookies_file:
        cookies_path = os.path.join('/tmp', cookies_file.filename)
        cookies_file.save(cookies_path)
        ydl_opts['cookiefile'] = cookies_path
    elif os.path.exists(FIXED_COOKIES_PATH):
        ydl_opts['cookiefile'] = FIXED_COOKIES_PATH

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Clean up uploaded cookies file if saved
        if cookies_file and os.path.exists(cookies_path):
            os.remove(cookies_path)

    return jsonify(info)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

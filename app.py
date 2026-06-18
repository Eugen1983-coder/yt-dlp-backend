from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/', methods=['POST'])
def handle_post():
    data = request.get_json(force=True)  # Parse JSON body
    print("Received POST request with data:", data)
    return jsonify({
        "status": "success",
        "message": "POST request received successfully",
        "receivedData": data
    })

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
#!/bin/sh

# Check if YOUTUBE_COOKIES_B64 is set
if [ -n "$YOUTUBE_COOKIES_B64" ]; then
  echo "Decoding YOUTUBE_COOKIES_B64 environment variable to /app/youtube_cookies.txt"
  echo "$YOUTUBE_COOKIES_B64" | base64 -d > /app/youtube_cookies.txt
else
  echo "Warning: YOUTUBE_COOKIES_B64 environment variable is not set. Continuing without cookie file."
fi

# Start the Flask app with Gunicorn
exec gunicorn -b 0.0.0.0:5000 app:app

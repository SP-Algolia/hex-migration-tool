import sys
import os

# Add the parent directory to the path so we can import our app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# This is the handler function that Vercel will call
def handler(request):
    return app(request.environ, lambda status, headers: None)

# For compatibility, also expose the app directly
application = app

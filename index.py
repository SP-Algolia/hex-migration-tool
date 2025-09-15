from app import app

# This is the WSGI callable for Vercel
application = app

if __name__ == "__main__":
    app.run(debug=False)

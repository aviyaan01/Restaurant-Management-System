from app import create_app

# Instantiate application using the factory
app = create_app()

if __name__ == '__main__':
    # Local development server
    app.run(host='0.0.0.0', port=5000)


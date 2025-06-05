from app import create_app
# Creează o instanță a aplicației Flask folosind factory-ul definit în __init__.py
app = create_app()
# Dacă acest fișier este rulat direct (nu importat), pornește serverul Flask
if __name__ == '__main__':
# Pornește serverul Flask
    app.run(debug=True)
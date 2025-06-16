from flask_login import UserMixin  # Import pentru clasa UserMixin, care ajută la integrarea cu Flask-Login

class User(UserMixin):
    # Constructorul clasei User primește un dicționar (user_dict) ce conține datele utilizatorului din MongoDB
    def __init__(self, user_dict):
        self.id = str(user_dict.get('_id'))  # ID-ul utilizatorului, convertit în string (necesar pentru Flask-Login)
        self.username = user_dict.get('username')  # Numele de utilizator
        self.role = user_dict.get('role')  # Rolul utilizatorului (ex: 'profesor')

from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, user_dict):
        self.id = str(user_dict.get('_id'))
        self.username = user_dict.get('username')
        self.role = user_dict.get('role')

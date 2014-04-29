from portality.authorise import Authorise
from portality import dao
from portality.core import app
import uuid
from datetime import datetime, timedelta

from werkzeug import generate_password_hash, check_password_hash
from flask.ext.login import UserMixin

class Account(dao.AccountDAO, UserMixin):
    @classmethod
    def make_account(cls, username, name=None, email=None, roles=[]):
        a = cls.pull(username)
        if a:
            return a

        a = Account(id=username)
        a.set_name(name) if name else None
        a.set_email(email) if email else None
        for role in roles:
            a.add_role(role)
        
        reset_token = uuid.uuid4().hex
        # give them 14 days to create their first password if timeout not specified in config
        a.set_reset_token(reset_token, app.config.get("PASSWORD_CREATE_TIMEOUT", app.config.get('PASSWORD_RESET_TIMEOUT', 86400) * 14))
        return a
    
    @property
    def name(self):
        return self.data.get("name")
    
    def set_name(self, name):
        self.data["name"] = name
    
    @property
    def email(self):
        return self.data.get("email")

    def set_email(self, email):
        self.data["email"] = email

    def set_password(self, password):
        self.data['password'] = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.data['password'], password)
        
    @property
    def reset_token(self): return self.data.get('reset_token')

    def set_reset_token(self, token, timeout):
        expires = datetime.now() + timedelta(0, timeout)
        self.data["reset_token"] = token
        self.data["reset_expires"] = expires.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def remove_reset_token(self):
        if "reset_token" in self.data:
            del self.data["reset_token"]
        if "reset_expires" in self.data:
            del self.data["reset_expires"]
    
    @property
    def is_super(self):
        # return not self.is_anonymous() and self.id in app.config['SUPER_USER']
        return Authorise.has_role(app.config["SUPER_USER_ROLE"], self.data.get("role", []))
    
    def has_role(self, role):
        return Authorise.has_role(role, self.data.get("role", []))
    
    def add_role(self, role):
        if "role" not in self.data:
            self.data["role"] = []
        self.data["role"].append(role)
    
    @property
    def role(self):
        return self.data.get("role", [])
    
    def set_role(self, role):
        if not isinstance(role, list):
            role = [role]
        self.data["role"] = role
            
    def prep(self):
        self.data['last_updated'] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")


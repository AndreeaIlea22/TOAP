import uuid
from flask.ext.login import UserMixin
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

from portality.dao import DomainObject as DomainObject
from portality.core import app
from portality.authorise import Authorise

class Account(DomainObject, UserMixin):
    __type__ = 'account'

    @classmethod
    def make_account(cls, username, name=None, email=None, roles=[], associated_journal_ids=[]):
        a = cls.pull(username)
        if a:
            return a

        a = Account(id=username)
        a.set_name(name) if name else None
        a.set_email(email) if email else None

        for role in roles:
            a.add_role(role)

        # If the api role was added, generate a key
        if "api" in roles:
            a.generate_api_key()

        for jid in associated_journal_ids:
            a.add_journal(jid)
        reset_token = uuid.uuid4().hex
        # give them 14 days to create their first password if timeout not specified in config
        a.set_reset_token(reset_token, app.config.get("PASSWORD_CREATE_TIMEOUT", app.config.get('PASSWORD_RESET_TIMEOUT', 86400) * 14))
        return a

    @classmethod
    def pull_by_email(cls, email):
        res = cls.query(q='email:"' + email + '"')
        if res.get('hits', {}).get('total', 0) == 1:
            return cls(**res['hits']['hits'][0]['_source'])
        else:
            return None

    @classmethod
    def get_by_reset_token(cls, reset_token, not_expired=True):
        res = cls.query(q='reset_token.exact:"' + reset_token + '"')
        obs = [hit.get("_source") for hit in res.get("hits", {}).get("hits", [])]
        if len(obs) == 0 or len(obs) > 1:
            return None
        expires = obs[0].get("reset_expires")
        if expires is None:
            return None
        if not_expired:
            try:
                ed = datetime.strptime(expires, "%Y-%m-%dT%H:%M:%SZ")
                if ed < datetime.now():
                    return None
            except:
                return None
        return cls(**obs[0])

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
    def journal(self):
        return self.data.get("journal")

    def add_journal(self, jid):
        if jid in self.data.get("journal", []):
            return
        if "journal" not in self.data:
            self.data["journal"] = []
        if jid not in self.data["journal"]:
            self.data["journal"].append(jid)

    def remove_journal(self, jid):
        if "journal" not in self.data:
            return
        self.data["journal"].remove(jid)

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

    @classmethod
    def all_top_level_roles(cls):
        return Authorise.top_level_roles()

    def add_role(self, role):
        if "role" not in self.data:
            self.data["role"] = []
        if role not in self.data["role"]:
            self.data["role"].append(role)
        # If we're adding the API role, ensure we also have a key to validate
        if role == 'api' and not self.data.get('api_key', None):
            self.generate_api_key()

    def remove_role(self, role):
        if "role" not in self.data:
            return
        if role in self.data["role"]:
            self.data["role"].remove(role)

    @property
    def role(self):
        return self.data.get("role", [])

    def set_role(self, role):
        if not isinstance(role, list):
            role = [role]
        self.data["role"] = role

    def prep(self):
        self.data['last_updated'] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    @property
    def api_key(self):
        if self.has_role('api'):
            # Return the stored api key if it's there, generate one if not (there should be one present if the role is)
            return self.data.get('api_key', self.generate_api_key())
        else:
            return None

    def generate_api_key(self):
        k = uuid.uuid4().hex
        self.data['api_key'] = k
        return k

    @classmethod
    def pull_by_api_key(cls, key):
        """Find a user by their API key - only succeed if they currently have API access."""
        res = cls.query(q='api_key.exact:"' + key + '"')
        if res.get('hits', {}).get('total', 0) == 1:
            usr = cls(**res['hits']['hits'][0]['_source'])
            if usr.has_role('api'):
                return usr
        return None


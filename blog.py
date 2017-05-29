import os
import re
import random
import hashlib
import hmac
from string import letters

import webapp2
import jinja2

from google.appengine.ext import db

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)

secret = 'biggetybiggetyboo'

def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)

def make_secure_val(val):
    return '%s|%s' % (val, hmac.new(secret, val).hexdigest())

def check_secure_val(secure_val):
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val

#-------------------------------Blog Handler------------------------------------

class BlogHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        params['user'] = self.user
        return render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

#---Set and read cookie securely---
    def set_secure_cookie(self, name, val):
        cookie_val = make_secure_val(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

#---login in and out with cookie---
    def login(self, user):
        self.set_secure_cookie('user_id', str(user.key().id()))

    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie('user_id')
        self.user = uid and User.by_id(int(uid))

def render_post(response, post):
    response.out.write('<b>' + post.subject + '</b><br>')
    response.out.write(post.content)

#----------------------User Password Security-----------------------------------

def make_salt(length = 5):
    return ''.join(random.choice(letters) for x in xrange(length))

def make_pw_hash(name, pw, salt = None):
    if not salt:
        salt = make_salt()
    h = hashlib.sha256(name + pw + salt).hexdigest()
    return '%s,%s' % (salt, h)

def valid_pw(name, password, h):
    salt = h.split(',')[0]
    return h == make_pw_hash(name, password, salt)

def users_key(group = 'default'):
    return db.Key.from_path('users', group)

#-------------------------User Table Modeler------------------------------------

class User(db.Model):
    name = db.StringProperty(required = True)
    pw_hash = db.StringProperty(required = True)
    email = db.StringProperty()

    @classmethod
    def by_id(cls, uid):
        return User.get_by_id(uid, parent = users_key())

    @classmethod
    def by_name(cls, name):
        u = User.all().filter('name =', name).get()
        return u

    @classmethod
    def register(cls, name, pw, email = None):
        pw_hash = make_pw_hash(name, pw)
        return User(parent = users_key(),
                    name = name,
                    pw_hash = pw_hash,
                    email = email)

    @classmethod
    def login(cls, name, pw):
        u = cls.by_name(name)
        if u and valid_pw(name, pw, u.pw_hash):
            return u

def blog_key(name = 'default'):
    return db.Key.from_path('blogs', name)

#----------------------------Post Table Modeler---------------------------------

class Post(db.Model):
    subject = db.StringProperty(required = True)
    content = db.TextProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now = True)
    user_id = db.StringProperty(required = True)
    likes = db.StringListProperty()
    parent = db.StringProperty()

    def render(self):
        self._render_text = self.content.replace('\n', '<br>')
        return render_str("post.html", p = self)

#-----------------------------Blog Front Page-----------------------------------

class BlogFront(BlogHandler):
    def get(self):
        posts = Post.all().filter('parent =', None).order('-created')
        uid = self.read_secure_cookie('user_id')

        self.render('front.html', posts = posts, uid=uid)

#--------------------------------Post Page--------------------------------------

class PostPage(BlogHandler):
    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        uid = self.read_secure_cookie('user_id')

        if post.likes and uid in post.likes:
            likeText = 'Unlike'
        elif uid == None:
            likeText = 'Login or sign up to like'
        else:
            likeText = 'Like'

        totalLikes = len(post.likes)

        comments = Post.all().filter('parent =', post_id)

        for comment in comments:
            print(comments)


        if not post:
            self.error(404)
            return

        post._render_text = post.content.replace('\n', '<br>')

        self.render("post.html", post = post, likeText = likeText, 
                    totalLikes = totalLikes, uid = uid, comments = comments)

    def post(self, post_id):
        if not self.user:
            self.redirect('/')

        subject = self.request.get('subject')
        content = self.request.get('content')

        uid = self.read_secure_cookie('user_id')

        if subject and content:
            post = Post(parent = blog_key(), subject = subject, 
                        content = content, user_id = uid, parent = post_id)
            post.put()
            self.redirect('/post/%s' % post_id)
        else:
            error = "subject and content, please!"
            self.render("post.html", subject=subject, content=content, 
                        error=error)

#-------------------Logs Like and puts uid into post table----------------------

class LikePage(BlogHandler):
    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        uid = self.read_secure_cookie('user_id')

        if not post:
            self.error(404)
            return

        if post.user_id != uid:

            if post.likes and uid in post.likes:
                post.likes.remove(uid)
            else:
                post.likes.append(uid)

            post.put()
            print(post.likes)

            self.redirect('/post/%s' % str(post.key().id()))

        else:
            error = "You cannot like or dislike your own post"
            self.render("error.html", error = error)

#-------------------Will Delete Post if UID is correct--------------------------

class DeletePage(BlogHandler):
    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        if not post:
            self.redirect("/")
            return

        uid = self.read_secure_cookie('user_id')

        if post.user_id != uid:
            error = "You cannot delete another user post"
        else:
            error = ''
            db.delete(key)

        self.render("delete.html", error = error)

#-----------------------Let's User Edit thier post------------------------------

class EditPage(BlogHandler):
    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        if not post:
            self.error(404)
            return

        uid = self.read_secure_cookie('user_id')

        if post.user_id != uid:
            error = 'You don\'t have permission to edit this post'
        else:
            error = ''

        self.render("edit.html", post = post, error = error, uid=uid)

    def post(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        uid = self.read_secure_cookie('user_id')

        subject = self.request.get('subject')
        content = self.request.get('content')

        if subject and content and post.user_id == uid:
            post.subject = subject
            post.content = content
            post.put()
            if post.parent:
                redirect_id = post.parent
            else:
                redirect_id = post.key().id()
            self.redirect('/post/%s' % str(redirect_id))
        else:
            error = "subject and content, please!"
            self.render("edit.html", post = post, error=error)

#---------------------------Creates a New Post----------------------------------

class NewPost(BlogHandler):
    def get(self):
        uid = self.read_secure_cookie('user_id')
        if self.user:
            self.render("newpost.html",  uid=uid)
        else:
            self.redirect("/login")

    def post(self):
        if not self.user:
            self.redirect('/login')

        subject = self.request.get('subject')
        content = self.request.get('content')

        uid = self.read_secure_cookie('user_id')

        if subject and content:
            post = Post(parent = blog_key(), subject = subject, 
                        content = content, user_id = uid)
            post.put()
            self.redirect('/post/%s' % str(post.key().id()))
        else:
            error = "subject and content, please!"
            self.render("newpost.html", subject=subject, content=content, 
                        error=error)

#---------------------Validations For New Account Creation----------------------

USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
def valid_username(username):
    return username and USER_RE.match(username)

PASS_RE = re.compile(r"^.{3,20}$")
def valid_password(password):
    return password and PASS_RE.match(password)

EMAIL_RE  = re.compile(r'^[\S]+@[\S]+\.[\S]+$')
def valid_email(email):
    return not email or EMAIL_RE.match(email)

#--------------------------Account Creation Handler-----------------------------

class Signup(BlogHandler):
    def get(self):
        self.render("signup.html")

    def post(self):
        have_error = False
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        self.verify = self.request.get('verify')
        self.email = self.request.get('email')

        params = dict(username = self.username,
                      email = self.email)

        if not valid_username(self.username):
            params['error_username'] = "That's not a valid username."
            have_error = True

        if not valid_password(self.password):
            params['error_password'] = "That wasn't a valid password."
            have_error = True
        elif self.password != self.verify:
            params['error_verify'] = "Your passwords didn't match."
            have_error = True

        if not valid_email(self.email):
            params['error_email'] = "That's not a valid email."
            have_error = True

        if have_error:
            self.render('signup.html', **params)
        else:
            self.done()

    def done(self, *a, **kw):
        raise NotImplementedError

#------------------------------Create New User----------------------------------

class Register(Signup):
    def done(self):
        u = User.by_name(self.username)
        if u:
            msg = 'That user already exists.'
            self.render('signup.html', error_username = msg)
        else:
            u = User.register(self.username, self.password, self.email)
            u.put()

            self.login(u)
            self.redirect('/')

#---------------------------------Blog login------------------------------------

class Login(BlogHandler):
    def get(self):
        self.render('login.html')

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')

        u = User.login(username, password)
        if u:
            self.login(u)
            self.redirect('welcome')
        else:
            msg = 'Invalid login'
            self.render('login.html', error = msg)

#--------------------------------User Logout------------------------------------

class Logout(BlogHandler):
    def get(self):
        self.logout()
        self.redirect('/')

#---------------------------Welcome page after login----------------------------

class Welcome(BlogHandler):
    def get(self):
        if self.user:
            uid = self.read_secure_cookie('user_id')
            self.render('welcome.html', username = self.user.name, uid=uid)
        else:
            self.redirect('/signup')

#---------------------------------site index------------------------------------

app = webapp2.WSGIApplication([('/?', BlogFront),
                               ('/post/([0-19]+)', PostPage),
                               ('/delete/([0-19]+)', DeletePage),
                               ('/edit/([0-19]+)', EditPage),
                               ('/like/([0-19]+)', LikePage),
                               ('/newpost', NewPost),
                               ('/signup', Register),
                               ('/login', Login),
                               ('/logout', Logout),
                               ('/welcome', Welcome),
                               ],
                              debug=True)

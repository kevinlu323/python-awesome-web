import asyncio, time, re, hashlib, json, logging
from coreweb import get, post
from aiohttp import web
from models import User, Blog, next_id
from api_errors import APIError, APIValueError, APIPermissionError
from config import configs

logging.basicConfig(level=logging.INFO)

_RE_EMAIL = re.compile(r'^[a-z0-z\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')
COOKIE_NAME = 'awesome'
_COOKIE_KEY = configs.session.secret
MAX_COOKIE_AGE = 86400


def user2cookie(user, max_age):
    # build cookie str
    expires = str(int(time.time() + max_age))
    s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
    L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(L)


async def cookie2user(cookie_str):
    if not cookie_str:
        return None
    try:
        L = cookie_str.split('-')
        if len(L) != 3:
            return None
        uid, expire, sha1 = L
        if int(expire) < time.time():
            return None
        user = await User.find(uid)
        if user is None:
            return None
        s = '%s-%s-%s-%s' % (user.id, user.passwd, expire, _COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.warning('Invalid sha1 found, cookie may be fake!!')
            return None
        user.passwd = '**********'
        return user
    except Exception as e:
        logging.exception(e)
        return None

def check_admin(request):
    if not request.__user__ or not request.__user__.admin:
        raise APIPermissionError('User has no permission to create blog!')

@get('/')
async def index(request):
    blogs = await Blog.findAll()
    blogs.extend([
        Blog(id='1', name='Test Blog - 1', summary='summary for blog 1', created_at=time.time() - 120),
        Blog(id='2', name='Test Blog - 2', summary='Hello world!', created_at=time.time() - 3600),
        Blog(id='3', name='last one for testing', summary='test test test test', created_at=time.time() - 86400)
    ])
    return {
        '__template__': 'blogs.html',
        'blogs': blogs
    }


@get('/api/users')
async def api_get_user():
    users = await User.findAll()
    for user in users:
        user.passwd = '**********'
    return dict(users=users)


@get('/register')
async def register():
    return {
        '__template__': 'register.html'
    }


@get('/login')
async def login():
    return {
        '__template__': 'login.html'
    }


@post('/api/users')
async def api_register_user(*, name, email, passwd):
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('passwd')
    users = await User.findAll('email=?', [email])
    if len(users) > 0:
        raise APIError('register:failed', 'email', 'Email address is already in use')
    uid = next_id()
    sha1_pass = '%s:%s' % (uid, passwd)
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_pass.encode('utf-8')).hexdigest(),
                image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    await user.save()
    # make session cookie
    r = web.Response()
    r.set_cookie(name=COOKIE_NAME, value=user2cookie(user, MAX_COOKIE_AGE), max_age=MAX_COOKIE_AGE, httponly=True)
    user.passwd = '**********'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r


@post('/api/authenticate')
async def authenticate(*, email, passwd):
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email', 'Invalid email address!')
    if not passwd:
        raise APIValueError('passwd', 'Invalid password!')
    users = await User.findAll('email=?', [email])
    if len(users) == 0:
        raise APIValueError('email', 'Email address is not existing')
    user = users[0]
    # check user password
    sha1_pass = '%s:%s' % (user.id, passwd)
    if user.passwd != hashlib.sha1(sha1_pass.encode('utf-8')).hexdigest():
        raise APIValueError('passwd', 'Wrong password!')
    # if authentication is ok, set cookie
    r = web.Response()
    r.set_cookie(name=COOKIE_NAME, value=user2cookie(user, MAX_COOKIE_AGE), max_age=MAX_COOKIE_AGE, httponly=True)
    user.passwd = '**********'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r


@get('/logout')
async def logout(request):
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted', max_age=0, httponly=True)
    logging.info('user logged out!')
    return r


@get('/manage/blogs/create')
async def manage_create_blog():
    return {
        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action': '/api/blogs'
    }


@get('/api/blogs/{id}')
async def api_get_blog(id):
    blog = await Blog.find(id)
    return blog


@post('/api/blogs')
async def api_create_blog(request, *, name, summary, content):
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name', 'blog name cannot be empty!')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'blog summary cannot be empty!')
    if not content or not content.strip():
        raise APIValueError('content', 'blog content cannot be empty!')
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image, name=name, summary=summary, content=content)
    await blog.save()
    return blog

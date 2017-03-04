import asyncio, time, re, hashlib, json, logging, markdown2
from coreweb import get, post
from aiohttp import web
from models import User, Blog, Comment, next_id
from apis import APIError, APIValueError, APIPermissionError, APIResourceNotFoundError, Page
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


def text2html(text):
    raw_lines = filter(lambda x: x.strip() != '', text.split('\n'))
    html_lines = map(lambda line: '<p>%s</p>' % line.replace('&', '&amp;').replace('<', '%lt;').replace('>', '&gt;'),
                     raw_lines)
    return ''.join(html_lines)


def get_page_index(page_str):
    p = 1
    try:
        p = int(page_str)
    except ValueError as e:
        logging.exception(e)
        pass
    if p < 1:
        p = 1
    return p


@get('/')
async def index(request):
    blogs = await Blog.findAll(orderBy='created_at desc')
    return {
        '__template__': 'blogs.html',
        'blogs': blogs
    }


@get('/blog/{id}')
async def get_blog(id):
    blog = await Blog.find(id)
    comments = await Comment.findAll(where='blog_id=?', args=[id], orderBy='created_at desc')
    # Convert plain text comment into html content
    for c in comments:
        c.html_content = text2html(c.content)
    blog.html_content = markdown2.markdown(blog.content)
    return {
        '__template__': 'blog.html',
        'blog': blog,
        'comments': comments
    }


@get('/api/users')
async def api_get_user(*, page='1'):
    page_index = get_page_index(page)
    num = await User.findNumber('count(id)')
    p = Page(item_count=num, page_index=page_index)
    if num == 0:
        return dict(page=p, users=())
    users = await User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, users=users)


@get('/api/blogs')
async def api_get_blogs(*, page='1'):
    page_index = get_page_index(page)
    num = await Blog.findNumber('count(id)')
    p = Page(item_count=num, page_index=page_index)
    if num == 0:
        return dict(page=p, blogs=())
    blogs = await Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, blogs=blogs)


@get('/api/comments')
async def api_get_comments(*, page='1'):
    page_index = get_page_index(page)
    num = await Comment.findNumber('count(id)')
    p = Page(item_count=num, page_index=page_index)
    if num == 0:
        return dict(page=p, comments=())
    comments = await Comment.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, comments=comments)


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


@post('/api/blogs/{id}/delete')
async def api_delete_blog(request, *, id):
    check_admin(request)
    blog = await Blog.find(id)
    if not blog:
        raise APIResourceNotFoundError('Blog', 'Failed to delete, blog not found')
    await blog.remove()
    return blog


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
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image,
                name=name, summary=summary, content=content)
    await blog.save()
    return blog


@post('/api/blogs/{id}/comments')
async def api_create_comments(id, request, *, content):
    if not content or not content.strip():
        raise APIValueError('content', 'comments content cannot be empty!')
    comment = Comment(blog_id=id, user_id=request.__user__.id, user_name=request.__user__.name,
                      user_image=request.__user__.image, content=content)
    await comment.save()
    return comment


@post('/api/comments/{id}/delete')
async def api_delete_comment(request, *, id):
    check_admin(request)
    comment = await Comment.find(id)
    if not comment:
        raise APIResourceNotFoundError('comment', 'Failed to delete comment, comment not found!')
    await comment.remove()
    return comment


@get('/manage/')
async def manage():
    return 'redirect:/manage/blogs'


@get('/manage/blogs')
async def manage_blogs(*, page='1'):
    return {
        '__template__': 'manage_blogs.html',
        'page_index': get_page_index(page)
    }


@get('/manage/comments')
async def manage_comments(*, page='1'):
    return {
        '__template__': 'manage_comments.html',
        'page_index': get_page_index(page)
    }


@get('/manage/users')
async def manage_users(*, page='1'):
    return {
        '__template__': 'manage_users.html',
        'page_index': get_page_index(page)
    }

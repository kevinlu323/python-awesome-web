import asyncio, time
from coreweb import get
from aiohttp import web
from models import User, Blog


@get('/')
async def index(request):
    users = await User.findAll()
    blogs = [
        Blog(id='1', name='Test Blog - 1', summary='summary for blog 1', created_at = time.time() - 120),
        Blog(id = '2', name='Test Blog - 2', summary = 'Hello world!', created_at = time.time() - 3600),
        Blog(id='3', name = 'last one for testing', summary = 'test test test test', created_at = time.time() - 86400)
    ]
    return {
        '__template__': 'blogs.html',
        'blogs':blogs
    }

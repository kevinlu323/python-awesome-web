import asyncio
from coreweb import get
from aiohttp import web
from models import User


@get('/')
async def index(request):
    users = await User.findAll()
    return {
        '__template__': 'test.html',
        'users':users
    }

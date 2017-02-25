import asyncio
from coreweb import get
from aiohttp import web


@get('/')
async def index(request):
    return 'Hello world'

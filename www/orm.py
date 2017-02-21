#user/bin/env python3
# -*- coding: utf-8 -*-

import asyncio,logging
import aiomysql

async def create_pool(loop, **kw):
    logging.info('creating database connection...')
    global _pool
    _pool = await aiomysql.create_pool(
        host = kw.get('host', 'localhost'),
        port = kw.get('port', 3306),
        user = kw['username'],
        password = kw['password'],
        db = kw['db'],
        charset = kw.get('charset', 'utf-8'),
        autocommit = kw.get('autocommit', True),
        maxsize = kw.get('maxsize', 10),
        minsize = kw.get('minsize', 1),
        loop = loop
    )
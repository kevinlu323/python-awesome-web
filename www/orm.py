# user/bin/env python3
# -*- coding: utf-8 -*-

import asyncio, logging

logging.basicConfig(level=logging.INFO)

import aiomysql


def log(sql, args=()):
    logging.info('SQL statement: %s' % sql)


async def create_pool(loop, **kw):
    logging.info('creating database connection...')
    global _pool
    _pool = await aiomysql.create_pool(
        host=kw.get('host', 'localhost'),
        port=kw.get('port', 3306),
        user=kw['username'],
        password=kw['password'],
        db=kw['db'],
        charset=kw.get('charset', 'utf-8'),
        autocommit=kw.get('autocommit', True),
        maxsize=kw.get('maxsize', 10),
        minsize=kw.get('minsize', 1),
        loop=loop
    )


async def select(sql, args, size=None):
    log(sql, args)
    global _pool
    async with _pool.get() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql.replace('?', '%s'), args or ())
            if size:
                rs = await cur.fetchmany(size)
            else:
                rs = await cur.fetchall()
        logging.info('row returned: %s' % len(rs))
        return rs


async def execute(sql, args, autocommit=True):
    log(sql, args)
    async with _pool.get() as conn:
        if not autocommit:
            await conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql.replace('?', '%s'), args)
                affected_row_count = await cur.rowcount
                if not autocommit:
                    await conn.commit()
        except BaseException as e:
            if not autocommit:
                await conn.rollback()
            raise
        return affected_row_count


# create arg string for sql, i.e, input num=3, return ?,?,?
def create_arg_str(num):
    L=[]
    for n in range(num):
        L.append('?')
        return ','.join(L)

# Base Field class
class Field(object):
    def __init__(self, name, column_type, is_primary_key, default_value):
        self.name = name
        self.column_type = column_type
        self.is_primary_key = is_primary_key
        self.default_value = default_value

        def __str__(self):
            return '<%s, %s:%s>' % (self.__class__.name, self.column_type, self.name)

        __repr__ = __str__


# Different type to map to different DB column_type
class StringField(Field):
    def __init__(self, name=None, is_primary_key=False, default_value=None, column_type='varchar(100)'):
        super.__init__(name, column_type, is_primary_key, default_value)


class Boolean(Field):
    def __init__(self, name=None, is_primary_key=False, default_value=False, column_type='boolean'):
        super.__init__(name, column_type, is_primary_key, default_value)


class IntegerField(Field):
    def __init__(self, name=None, is_primary_key=False, default_value=0, column_type='bigint'):
        super.__init__(name, column_type, is_primary_key, default_value)


class FloatField(Field):
    def __init__(self, name=None, is_primary_key=False, default_value=0.0, column_type='real'):
        super.__init__(name, column_type, is_primary_key, default_value)


class TextField(Field):
    def __init__(self, name=None, is_primary_key=False, default_value=None, column_type='text'):
        super.__init__(name, column_type, is_primary_key, default_value)

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
        charset=kw.get('charset', 'utf8'),
        autocommit=kw.get('autocommit', True),
        maxsize=kw.get('maxsize', 10),
        minsize=kw.get('minsize', 1),
        loop=loop
    )


async def destroy_pool():
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()


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
                logging.info(sql)
                await cur.execute(sql.replace('?', '%s'), args)
                affected_row_count = cur.rowcount
                if not autocommit:
                    await conn.commit()
        except BaseException as e:
            if not autocommit:
                await conn.rollback()
            raise
        return affected_row_count


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
        super(StringField, self).__init__(name, column_type, is_primary_key, default_value)


class BooleanField(Field):
    def __init__(self, name=None, is_primary_key=False, default_value=False, column_type='boolean'):
        super(BooleanField, self).__init__(name, column_type, is_primary_key, default_value)


class IntegerField(Field):
    def __init__(self, name=None, is_primary_key=False, default_value=0, column_type='bigint'):
        super(IntegerField, self).__init__(name, column_type, is_primary_key, default_value)


class FloatField(Field):
    def __init__(self, name=None, is_primary_key=False, default_value=0.0, column_type='real'):
        super(FloatField, self).__init__(name, column_type, is_primary_key, default_value)


class TextField(Field):
    def __init__(self, name=None, is_primary_key=False, default_value=None, column_type='text'):
        super(TextField, self).__init__(name, column_type, is_primary_key, default_value)


# create arg string for sql, i.e, input num=3, return ?,?,?
def create_arg_str(num):
    L = []
    for i in range(num):
        L.append('?')
    return ','.join(L)


class ModelMetaclass(type):
    def __new__(cls, name, bases, attrs):
        # for base class 'Model', do nothing
        if name == 'Model':
            return super(ModelMetaclass, cls).__new__(cls, name, bases, attrs)
        table_name = attrs.get('__table__', None) or name
        logging.info('Found model: name=%s, (tableName=%s)' % (name, table_name))
        mappings = dict()
        fields = []
        primary_key = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('--found field mapping: %s==>%s' % (k, v))
                mappings[k] = v
                if v.is_primary_key:
                    if primary_key:
                        logging.error('Duplicated primary key found for field %s' % (k,))
                        raise ValueError('Duplicated primary key found for field %s' % (k,))
                    primary_key = k
                else:
                    fields.append(k)
        if not primary_key:
            raise ValueError('Primary key not found for table name \'%s\'' % name)
        # remove mapped field from original attrs
        for k in mappings.keys():
            attrs.pop(k)
        escaped_field = list(map(lambda x: '`%s`' % x, fields))
        # re-assemble attrs for Model sub-classes
        attrs['__mappings__'] = mappings
        attrs['__table__'] = table_name
        attrs['__primary_key__'] = primary_key
        attrs['__fields__'] = fields
        attrs['__select__'] = 'SELECT `%s`,%s FROM %s' % (primary_key, ','.join(escaped_field), table_name)
        attrs['__insert__'] = 'INSERT INTO `%s` (%s, %s) VALUES (%s)' % (
            table_name, ','.join(escaped_field), primary_key, create_arg_str(len(escaped_field) + 1))
        attrs['__update__'] = 'UPDATE `%s` SET %s WHERE `%s`=?' % (
            table_name, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primary_key)
        attrs['__delete__'] = 'DELETE FROM %s WHERE `%s`=?' % (table_name, primary_key)
        return super(ModelMetaclass, cls).__new__(cls, name, bases, attrs)


class Model(dict, metaclass=ModelMetaclass):
    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError('\'Model\' object has no attribute: %s' % key)

    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None)

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default_value is not None:
                value = field.default_value() if callable(field.default_value) else field.default_value
                logging.info('use default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        return value

    # find objects with SQL WHERE clause
    @classmethod
    async def findAll(cls, where=None, args=None, **kw):
        sql = [cls.__select__]
        if where:
            sql.append('WHERE')
            sql.append(where)
        if args is None:
            args = []
        orderBy = kw.get('orderBy', None)
        if orderBy:
            sql.append('ORDER BY')
            sql.append(orderBy)
        limit = kw.get('limit', None)
        if limit:
            sql.append('LIMIT')
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?, ?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value %s' % str(limit))
        rs = await select(' '.join(sql), args)
        return [cls(**r) for r in rs]

    @classmethod
    async def findNumber(cls, selectFields, where=None, args=None):
        sql = ['SELECT %s _num_ FROM %s' % (selectFields, cls.__table__)]
        if where:
            sql.append('WHERE')
            sql.append(where)
        rs = await select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        return rs[0]['_num_']

    @classmethod
    async def find(cls, primary_key):
        rs = await select('%s WHERE `%s`=?' % (cls.__select__, cls.__primary_key__), [primary_key], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        logging.info('SQL args: %s' % args)
        rows = await execute(self.__insert__, args)
        if rows != 1:
            logging.error('Failed to insert record, affected rows: %s' % rows)

    async def update(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.error('Failed to update record, affected rows: %s' % rows)

    async def remove(self):
        args = [self.getValueOrDefault(self.__primary_key__)]
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.error('Failed to delete record, affected rows: %s' % rows)

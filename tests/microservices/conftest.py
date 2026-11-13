"""Integración real HTTP/PostgreSQL. Solo admite una base aislada invax_test*."""
import multiprocessing
import os
from pathlib import Path
import secrets
import socket
import time

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import pytest
import requests

ROOT = Path(__file__).resolve().parents[2]


def run_service(name, url, urls, cluster, secret, port, ready):
    import logging
    from werkzeug.serving import make_server
    from backend.microservices.common import HttpClient
    from backend.microservices.gateway import create_gateway
    from backend.microservices.services import create_auth, create_products, create_movements
    from backend.microservices.stores import AuthStore, ProductStore
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    os.environ.pop('DATABASE_PASSWORD', None)
    client = HttpClient(urls, cluster, name, connect_timeout=.4, read_timeout=5)
    if name == 'auth':
        store = AuthStore(url)
        store.asegurar_usuarios_iniciales('AdminPrueba2026!', 'VentaPrueba2026!')
        app = create_auth(store, secret, cluster)
    elif name == 'productos':
        app = create_products(ProductStore(url), client, cluster)
    elif name == 'gateway':
        app = create_gateway(client)
    else:
        app = create_movements(name, client, cluster)
    server = make_server('127.0.0.1', port, app, threaded=True)
    ready.send(True)
    ready.close()
    server.serve_forever()


class Stack:
    def __init__(self, auth_url, product_url):
        self.cluster = secrets.token_urlsafe(36)
        self.secret = secrets.token_bytes(32)
        self.database_urls = {'auth': auth_url, 'productos': product_url}
        self.urls, self.processes, self.ports = {}, {}, {}
        self.context = multiprocessing.get_context('spawn')
        for name in ('auth', 'productos', 'ventas', 'reposiciones', 'gateway'):
            with socket.socket() as s:
                s.bind(('127.0.0.1', 0))
                self.ports[name] = s.getsockname()[1]
            self.urls[name] = f'http://127.0.0.1:{self.ports[name]}'
            self.start(name)
        self.base = self.urls['gateway']

    def start(self, name):
        recv, send = self.context.Pipe(duplex=False)
        p = self.context.Process(target=run_service, args=(name, self.database_urls.get(name), dict(self.urls), self.cluster, self.secret, self.ports[name], send), daemon=True)
        p.start();send.close()
        self.processes[name] = p
        if not recv.poll(20):
            self.close();raise RuntimeError('No inició '+name)
        recv.recv();recv.close()

    def stop(self, name):
        self.processes[name].terminate();self.processes[name].join(5)

    def close(self):
        for p in self.processes.values():
            if p.is_alive():p.terminate()
            p.join(5)

    def request(self, method, path, **kwargs):
        return requests.request(method, self.base+path, timeout=15, **kwargs)

    def login(self, user='admin', password='AdminPrueba2026!'):
        r = self.request('POST', '/api/login', json={'usuario': user, 'clave': password})
        assert r.status_code == 200, r.text
        return {'Authorization': 'Bearer '+r.json()['token']}


@pytest.fixture(scope='session')
def database():
    url = os.environ.get('INVAX_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Configura INVAX_TEST_DATABASE_URL para integración PostgreSQL real.')
    params = conninfo_to_dict(url)
    if not params.get('dbname', '').startswith('invax_test'):
        pytest.fail('Las pruebas solo operan sobre bases cuyo nombre empieza por invax_test.')
    pwd = secrets.token_urlsafe(24)
    with psycopg.connect(url, autocommit=True) as c:
        for role in ('anon', 'authenticated'):
            if not c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
                c.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
        c.execute((ROOT/'database/01_tablas.sql').read_text())
        c.execute((ROOT/'database/02_microservices.sql').read_text())
        for role in ('invax_auth', 'invax_productos'):
            c.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(role), sql.Literal(pwd)))
        c.execute('TRUNCATE public.usuarios,public.operaciones,public.auditoria RESTART IDENTITY')
    auth_url = make_conninfo(url, user='invax_auth', password=pwd)
    product_url = make_conninfo(url, user='invax_productos', password=pwd)
    # Stores exigen un URI. make_conninfo devuelve DSN; convertir de forma privada.
    from urllib.parse import quote
    def uri(role):
        return f"postgresql://{role}:{quote(pwd,safe='')}@{params.get('host','127.0.0.1')}:{params.get('port','5432')}/{params['dbname']}"
    return url, uri('invax_auth'), uri('invax_productos')


@pytest.fixture(scope='session')
def cluster(database):
    stack = Stack(database[1], database[2])
    yield stack
    stack.close()


@pytest.fixture(autouse=True)
def reset_catalog(cluster, database):
    with psycopg.connect(database[0]) as c:
        c.execute('TRUNCATE public.productos,public.operaciones,public.auditoria RESTART IDENTITY')
        c.execute("INSERT INTO public.productos VALUES ('P001','Laptop',15000,10,0),('P002','Mouse',350,25,0),('P003','Teclado',700,15,0),('P004','Monitor',4500,8,0)")
    yield

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from backend.microservices.common import HttpClient, ServiceError, internal_app
from backend.microservices.gateway import create_gateway
from backend.microservices.stores import metadata, movement_data


@pytest.fixture
def stub():
    class Handler(BaseHTTPRequestHandler):
        calls = 0
        kind = 'bad-json'
        def do_POST(self):
            Handler.calls += 1
            if Handler.kind == 'slow':time.sleep(.2)
            self.send_response(200);self.end_headers()
            try:self.wfile.write(b'not-json')
            except BrokenPipeError:pass
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield Handler,server.server_address[1]
    server.shutdown();server.server_close();thread.join()


def test_invalid_json_and_timeout_do_not_retry(stub):
    handler,port=stub
    client=HttpClient({'auth':f'http://127.0.0.1:{port}'},'test-only-cluster-'*3,'gateway',read_timeout=.05)
    for kind in ('bad-json','slow'):
        handler.kind=kind
        before=handler.calls
        with pytest.raises(ServiceError) as e:client.call('auth','ping',[])
        assert e.value.status==503
        assert handler.calls==before+1


def test_internal_rpc_rejects_forgery_unknown_method_and_arguments():
    token='test-only-internal-'*3
    c=internal_app('test',token,{'ping':lambda:{'exito':True}}).test_client()
    assert c.post('/internal/rpc',json={'method':'ping','args':[]}).status_code==401
    h={'X-Cluster-Token':token,'X-Request-ID':'trace-ok'}
    assert c.post('/internal/rpc',headers=h,json={'method':'private_python_method','args':[]}).status_code==404
    assert c.post('/internal/rpc',headers=h,json={'method':'ping','args':[1]}).status_code==400
    r=c.post('/internal/rpc',headers=h,json={'method':'ping','args':[]})
    assert r.status_code==200 and r.headers['X-Request-ID']=='trace-ok'


def test_cors_allowlist_and_no_role_header_authority(monkeypatch):
    monkeypatch.setenv('INVAX_ALLOWED_ORIGINS','https://allowed.example')
    client=HttpClient({},'cluster-only-tests-'*3,'gateway')
    c=create_gateway(client).test_client()
    r=c.options('/api/productos',headers={'Origin':'https://allowed.example'})
    assert r.headers['Access-Control-Allow-Origin']=='https://allowed.example'
    assert 'Access-Control-Allow-Origin' not in c.options('/api/productos',headers={'Origin':'https://other.example'}).headers
    assert c.get('/api/productos',headers={'X-Role':'administrador'}).status_code==401
    monkeypatch.setenv('INVAX_ALLOWED_ORIGINS','*')
    with pytest.raises(RuntimeError):create_gateway(client)


@pytest.mark.parametrize('data',[{'id':'P005','nombre':'','precio':2},{'id':'P005','nombre':'X','precio':'NaN'},{'id':'P005','nombre':'X','precio':'1.001'},{'id':'P005','nombre':'X','precio':True},{'id':'P005','nombre':'X','precio':3,'cantidad':-1}])
def test_product_data_validation(data):
    with pytest.raises(ServiceError):metadata(data,True)


def test_parallel_diagnostics_keep_incoming_trace(monkeypatch):
    import threading
    seen = []
    lock = threading.Lock()
    def call(self, service, method, args, *, request_id=None):
        with lock:
            seen.append((service, request_id))
        return {"exito": True}, 200
    monkeypatch.setattr(HttpClient, "call", call)
    client = HttpClient({}, "diagnostic-tests-only-"*3, "gateway")
    app = create_gateway(client)
    # Authorization is covered separately; here exercise the router inside request context.
    from backend.microservices.gateway import GatewayRouter
    with app.test_request_context(headers={"X-Request-ID": "trace-diagnostics"}):
        app.preprocess_request()
        states = GatewayRouter(client).estado()
    assert len(states) == 4 and all(s["disponible"] for s in states)
    assert {rid for _, rid in seen} == {"trace-diagnostics"}

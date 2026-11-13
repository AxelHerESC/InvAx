from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import json
import psycopg
import pytest
import requests


def movement(product='P001', quantity=1):
    return {'id_producto': product, 'cantidad': quantity, 'request_id': str(uuid4())}


def test_gateway_http_and_pwa(cluster):
    for path in ('/', '/manifest.webmanifest', '/sw.js', '/assets/offline-store.js', '/api/health'):
        r = cluster.request('GET', path)
        assert r.status_code == 200
        assert r.headers['X-Request-ID']
    assert cluster.request('GET', '/api/salud').json()['microservicios'] is True
    assert cluster.request('GET', '/api/listo').status_code == 200
    r = cluster.request('GET', '/api/productos')
    assert r.status_code == 401
    for name in ('auth', 'productos', 'ventas', 'reposiciones'):
        r = requests.post(cluster.urls[name]+'/internal/rpc', json={'method': 'ping', 'args': []}, timeout=5)
        assert r.status_code == 401


def test_auth_permissions_and_untrusted_role(cluster):
    bad = cluster.request('POST', '/api/login', json={'usuario':'admin','clave':'incorrecta'})
    assert bad.status_code == 401
    seller = cluster.login('vendedor','VentaPrueba2026!')
    admin = cluster.login()
    for headers in ({'Authorization':'Bearer inventado'}, {}):
        assert cluster.request('GET','/api/productos',headers=headers).status_code == 401
    spoof = {**seller,'X-Role':'administrador','X-Cluster-Token':cluster.cluster}
    assert cluster.request('POST','/api/reposiciones',headers=spoof,json=movement()).status_code == 403
    # Incluso con la credencial interna, productos vuelve a autorizar al vendedor.
    r = requests.post(cluster.urls['productos']+'/internal/rpc',headers={'X-Cluster-Token':cluster.cluster},json={'method':'stock','args':[seller['Authorization'].split(' ')[1],'agregar_stock','P001',1,str(uuid4())]},timeout=10)
    assert r.status_code == 403
    assert cluster.request('POST','/api/ventas',headers=admin,json=movement()).status_code == 403
    assert cluster.request('GET','/api/auditoria',headers=seller).status_code == 403
    assert cluster.request('POST','/api/productos',headers=seller,json={'id':'P010','nombre':'X','precio':1}).status_code == 403


def test_crud_product_and_optimistic_version(cluster):
    h=cluster.login()
    data={'id':'P010','nombre':'Producto nuevo','precio':12.50,'cantidad':0}
    assert cluster.request('POST','/api/productos',headers=h,json=data).status_code == 201
    assert cluster.request('POST','/api/productos',headers=h,json=data).status_code == 409
    r=cluster.request('PATCH','/api/productos/P010',headers=h,json={'nombre':'Editado','precio':15,'version':0})
    assert r.status_code == 200
    assert cluster.request('PUT','/api/productos/P010',headers=h,json={'nombre':'Obsoleto','version':0}).status_code == 409
    assert cluster.request('PATCH','/api/productos/P010',headers=h,json={'cantidad':100,'version':1}).status_code == 422
    assert cluster.request('DELETE','/api/productos/P010',headers=h,json={'version':1}).status_code == 200
    assert cluster.request('GET','/api/productos/P010',headers=h).status_code == 404
    assert cluster.request('DELETE','/api/productos/P001',headers=h,json={'version':0}).status_code == 409


def test_sales_replenishments_ledger_trace_and_audit(cluster,database):
    admin=cluster.login();seller=cluster.login('vendedor','VentaPrueba2026!')
    op=movement(quantity=3)
    h={**seller,'X-Request-ID':'prueba-traza-123'}
    for _ in range(2):
        r=cluster.request('POST','/api/ventas',headers=h,json=op)
        assert r.status_code == 200
        assert r.headers['X-Request-ID']=='prueba-traza-123'
        assert r.json()['stock_actual']==7
    assert r.json()['repetida'] is True
    assert cluster.request('POST','/api/ventas',headers=seller,json={**op,'cantidad':2}).status_code==409
    restock=movement(quantity=4)
    for _ in range(2):
        r=cluster.request('POST','/api/reposiciones',headers=admin,json=restock)
        assert r.status_code==200 and r.json()['stock_actual']==11
    with psycopg.connect(database[0]) as c:
        assert c.execute('SELECT count(*) FROM public.operaciones').fetchone()[0]==2
        assert c.execute("SELECT count(*) FROM public.auditoria WHERE accion IN ('vender','agregar_stock')").fetchone()[0]==2
    assert len(cluster.request('GET','/api/ventas',headers=seller).json()['operaciones'])==1
    assert len(cluster.request('GET','/api/reposiciones',headers=admin).json()['operaciones'])==1
    assert cluster.request('GET','/api/reposiciones',headers=seller).status_code==403
    assert cluster.request('GET','/api/auditoria',headers=admin).status_code==200


def test_real_postgres_concurrent_sales_and_same_uuid(cluster,database):
    h=cluster.login('vendedor','VentaPrueba2026!')
    def sale(_):
        r=cluster.request('POST','/api/ventas',headers=h,json=movement('P004',3))
        return r.status_code
    with ThreadPoolExecutor(max_workers=6) as pool:
        codes=list(pool.map(sale,range(6)))
    assert codes.count(200)==2
    assert codes.count(409)==4
    op=movement('P001',2)
    with ThreadPoolExecutor(max_workers=6) as pool:
        answers=list(pool.map(lambda _:cluster.request('POST','/api/ventas',headers=h,json=op),range(6)))
    assert all(r.status_code==200 for r in answers)
    with psycopg.connect(database[0]) as c:
        assert c.execute("SELECT cantidad FROM public.productos WHERE id_producto='P004'").fetchone()[0]==2
        assert c.execute("SELECT cantidad FROM public.productos WHERE id_producto='P001'").fetchone()[0]==8
        assert c.execute('SELECT count(*) FROM public.operaciones WHERE request_id=%s',(op['request_id'],)).fetchone()[0]==1


def test_lost_response_can_recover_from_ledger(cluster):
    h=cluster.login('vendedor','VentaPrueba2026!');op=movement()
    first=cluster.request('POST','/api/ventas',headers=h,json=op)
    assert first.status_code==200
    # Simula perder el resultado en el cliente y reenviar exactamente la operación.
    r=cluster.request('POST','/api/ventas',headers=h,json=op)
    assert r.status_code==200 and r.json()['repetida'] and r.json()['stock_actual']==9


@pytest.mark.parametrize('value',[0,-1,True,1.5,'2',10001,None])
def test_invalid_quantities(cluster,value):
    h=cluster.login('vendedor','VentaPrueba2026!')
    assert cluster.request('POST','/api/ventas',headers=h,json=movement(quantity=value)).status_code==400


@pytest.mark.parametrize('name,path', [('ventas','/api/ventas'),('reposiciones','/api/reposiciones')])
def test_individual_failure_leaves_catalog_running(cluster,name,path):
    h=cluster.login('vendedor','VentaPrueba2026!') if name=='ventas' else cluster.login()
    cluster.stop(name)
    try:
        assert cluster.request('POST',path,headers=h,json=movement()).status_code==503
        assert cluster.request('GET','/api/productos',headers=h).status_code==200
        states=cluster.request('GET','/api/servidores',headers=h).json()['servidores']
        assert next(s for s in states if s['servidor']==name)['disponible'] is False
    finally:
        cluster.start(name)


def test_database_permissions_are_enforced(database):
    with psycopg.connect(database[1],autocommit=True) as auth:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):auth.execute('SELECT * FROM public.productos')
        with pytest.raises(psycopg.errors.InsufficientPrivilege):auth.execute('DELETE FROM public.operaciones')
    with psycopg.connect(database[2],autocommit=True) as product:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):product.execute('SELECT * FROM public.usuarios')
        with pytest.raises(psycopg.errors.InsufficientPrivilege):product.execute('DELETE FROM public.operaciones')
        with pytest.raises(psycopg.errors.InsufficientPrivilege):product.execute('SELECT * FROM public.auditoria')


def test_new_user_and_password_compatibility(cluster):
    h=cluster.login();name='u_'+uuid4().hex[:10]
    assert cluster.request('POST','/api/usuarios',headers=h,json={'usuario':name,'clave':'InicialPrueba2026!','rol':'vendedor'}).status_code==201
    token=cluster.login(name,'InicialPrueba2026!')
    assert cluster.request('PUT','/api/clave',headers=token,json={'clave_actual':'InicialPrueba2026!','clave_nueva':'NuevaPrueba2026!'}).status_code==200
    assert cluster.request('POST','/api/login',json={'usuario':name,'clave':'InicialPrueba2026!'}).status_code==401
    cluster.login(name,'NuevaPrueba2026!')

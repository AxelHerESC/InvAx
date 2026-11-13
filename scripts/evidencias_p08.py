"""Pruebas manuales contra el Gateway sin imprimir credenciales ni tokens completos."""
import argparse
from getpass import getpass
from uuid import uuid4
import requests


def main():
    p=argparse.ArgumentParser()
    p.add_argument('url',help='URL HTTPS del Gateway o http://127.0.0.1:8080')
    args=p.parse_args()
    user=input('Usuario: ').strip();password=getpass('Contraseña de InvAx: ')
    with requests.Session() as session:
        session.trust_env=False
        r=session.post(args.url.rstrip('/')+'/api/login',json={'usuario':user,'clave':password},timeout=(2,30))
        password=None
        if r.status_code!=200:raise SystemExit('Inicio de sesión rechazado: HTTP '+str(r.status_code))
        token=r.json()['token'];headers={'Authorization':'Bearer '+token,'X-Request-ID':str(uuid4())}
        for path in ('/api/sesion','/api/productos','/api/servidores','/api/ventas'):
            response=session.get(args.url.rstrip('/')+path,headers=headers,timeout=(2,30))
            data=response.json()
            if path=='/api/sesion':data={k:v for k,v in data.items() if k in ('usuario','rol','exito')}
            print(path,'HTTP',response.status_code,'X-Request-ID:',response.headers.get('X-Request-ID'))
            print(data)
        if input('¿Comprobar rechazo de reposición con cantidad 1? Escribe SI: ')=='SI':
            if r.json()['rol']!='vendedor':raise SystemExit('Esta prueba debe ejecutarse con vendedor para no modificar existencias.')
            response=session.post(args.url.rstrip('/')+'/api/reposiciones',headers=headers,json={'id_producto':'P001','cantidad':1,'request_id':str(uuid4())},timeout=(2,30))
            print('Reposición como vendedor: HTTP',response.status_code,response.json().get('mensaje'))


if __name__=='__main__':main()

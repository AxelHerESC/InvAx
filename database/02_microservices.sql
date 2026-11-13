-- Migración aditiva. No borra tablas ni modifica las cuentas de InvAx.
BEGIN;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='invax_auth') THEN
    CREATE ROLE invax_auth LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='invax_productos') THEN
    CREATE ROLE invax_productos LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END $$;
GRANT USAGE ON SCHEMA public TO invax_auth, invax_productos;
GRANT SELECT, INSERT, UPDATE ON public.usuarios TO invax_auth;
GRANT SELECT, INSERT ON public.auditoria TO invax_auth;
GRANT USAGE ON SEQUENCE public.auditoria_id_seq TO invax_auth, invax_productos;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.productos TO invax_productos;
GRANT SELECT, INSERT ON public.operaciones TO invax_productos;
GRANT INSERT ON public.auditoria TO invax_productos;

DROP POLICY IF EXISTS invax_auth_usuarios ON public.usuarios;
CREATE POLICY invax_auth_usuarios ON public.usuarios TO invax_auth USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS invax_auth_auditoria ON public.auditoria;
CREATE POLICY invax_auth_auditoria ON public.auditoria TO invax_auth USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS invax_productos_catalogo ON public.productos;
CREATE POLICY invax_productos_catalogo ON public.productos TO invax_productos USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS invax_productos_operaciones ON public.operaciones;
CREATE POLICY invax_productos_operaciones ON public.operaciones TO invax_productos USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS invax_productos_auditoria ON public.auditoria;
CREATE POLICY invax_productos_auditoria ON public.auditoria FOR INSERT TO invax_productos WITH CHECK (true);
COMMIT;
-- Configurar contraseñas de estos roles por un canal privado antes de usarlos.
-- No conceder estos roles a anon/authenticated ni al usuario del Gateway.

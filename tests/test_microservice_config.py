"""Límites de secretos y exposición en los manifiestos entregados."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_compose_ownership_and_only_gateway_exposed():
    config = yaml.safe_load((ROOT/"compose.microservices.yaml").read_text())
    services = config["services"]
    assert set(services) == {"gateway", "auth", "productos", "ventas", "reposiciones"}
    assert config["networks"]["core"]["internal"] is True
    for name, service in services.items():
        env = service["environment"]
        assert ("DATABASE_URL" in env) == (name in {"auth", "productos"})
        assert ("INVENTARIO_TOKEN_SECRET" in env) == (name == "auth")
        assert bool(service.get("ports")) == (name == "gateway")
        assert service["build"]["dockerfile"] == "deploy/microservices/Dockerfile"


def test_render_services_use_new_names_and_separate_credentials():
    config = yaml.safe_load((ROOT/"render-p08-free.yaml").read_text())
    assert len(config["services"]) == 5
    for group in config["envVarGroups"]:
        assert all(v.get("sync") is not False for v in group["envVars"])
    for service in config["services"]:
        assert service["name"].startswith("invax-p08-")
        assert service["plan"] == "free"
        env = {v["key"]: v for v in service["envVars"] if "key" in v}
        name = env["INVAX_SERVICE"]["value"]
        assert ("DATABASE_URL" in env) == (name in {"auth", "productos"})
        assert ("INVENTARIO_TOKEN_SECRET" in env) == (name == "auth")
        assert service["healthCheckPath"] == "/api/health"

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    postgres_dsn: str = "postgresql://archon:archon_dev@localhost:5432/archon"
    redis_url: str = "redis://localhost:6379/0"
    bind: str = "127.0.0.1:50051"
    metrics_port: int = 9100
    model_url: str = "http://localhost:8000/v1"
    model_name: str = ""
    model_api_key: str = ""
    api_token: str = ""
    sandbox_image: str = "archon-sandbox:dev"
    allowed_repo_hosts: frozenset[str] = frozenset({"github.com"})
    tls_cert: str = ""
    tls_key: str = ""
    tls_ca: str = ""

    @classmethod
    def from_env(cls):
        defaults = cls()
        values = {}
        for name in cls.__dataclass_fields__:
            value = os.getenv(f"ARCHON_{name.upper()}")
            if value is None:
                continue
            if name == "metrics_port":
                value = int(value)
            elif name == "allowed_repo_hosts":
                value = frozenset(item.strip() for item in value.split(",") if item.strip())
            values[name] = value
        return cls(**{name: values.get(name, getattr(defaults, name)) for name in cls.__dataclass_fields__})

from __future__ import annotations

from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

from configs_loader import load_config


if __name__ == "__main__":
    cfg = load_config("configs/pipeline_config.yaml")
    uri = cfg["neo4j_uri"]
    user = cfg["neo4j_user"]
    password = cfg["neo4j_password"]

    print(f"[neo4j] uri={uri}")
    print(f"[neo4j] user={user}")

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            result = session.run("RETURN 1 AS ok")
            row = result.single()
            print(f"[neo4j] connection ok, query result={row['ok']}")
        driver.close()
    except AuthError as exc:
        print("[neo4j] authentication failed: reached the server, but username/password was rejected")
        print(exc)
        raise
    except ServiceUnavailable as exc:
        print("[neo4j] service unavailable: cannot reach the server or TLS/URI is incorrect")
        print(exc)
        raise

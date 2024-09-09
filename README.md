# zara

Describe your project here.


To run keycloak locally:

```bash
docker run -p 8080:8080 -e KEYCLOAK_ADMIN=admin -e KEYCLOAK_ADMIN_PASSWORD=admin quay.io/keycloak/keycloak:latest start-dev
```

to create a migration:

```bash
uv run migrate.py --create "intial"
```


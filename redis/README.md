# Redis en la biblioteca virtual

Redis cumple cuatro funciones dentro del sistema:

1. **Sesiones** de usuario (`sess:<sid>`), con cookie `sid` `HttpOnly`.
2. **Cache-aside** de búsquedas y fichas (`cache:*`).
3. **Contadores** de visitas y favoritos (`cnt:*`).
4. **Ranking** de títulos populares (`rank:popular`), un sorted set.

La implementación vive en `app/auth/session.py` y `app/cache.py`. El panel de
administración reutiliza la misma invalidación: al crear, editar o borrar un
título elimina `cache:title:*`, `cache:search:*` y `cache:api:*`.

## Mapa de claves

| Clave | Tipo | Contenido | TTL |
| --- | --- | --- | --- |
| `sess:<sid>` | hash | `user_id` de la sesión | 7 días (`SESSION_TTL_SECONDS`) |
| `cache:search:<db>:<hash>` | string JSON | `total`, `page`, `results` de una búsqueda | 60 s |
| `cache:title:<db>:<id>` | string JSON | ficha serializada + promedio de notas | 300 s |
| `cache:api:<db>:<hash>` | string JSON | resultados de una búsqueda externa (Jikan/TMDB) | 600 s |
| `cnt:views:<id>` | string entero | visitas acumuladas a la ficha | sin TTL |
| `cnt:likes:<id>` | string entero | favoritos actuales del título | sin TTL |
| `rank:popular` | sorted set | título → visitas | sin TTL |

El sufijo `<db>` es el nombre de la base MongoDB (`catalogo` o una base de
pruebas), para que una misma instancia de Redis no mezcle cache entre bases.

## Comandos útiles

```powershell
redis-cli ping
redis-cli keys "sess:*"
redis-cli ttl "sess:<sid>"
redis-cli get "cnt:views:<title_id>"
redis-cli zrevrange rank:popular 0 9 withscores
redis-cli --scan --pattern "cache:*"
redis-cli flushdb   # solo para desarrollo o pruebas
```

## Decisiones de implementación

- **RESP2 obligatorio**: el build 5.0.14.1 para Windows no soporta `HELLO 3`;
  el cliente se crea con `protocol=2`. Sin eso, redis-py 8 falla con
  `unknown command 'HELLO'`.
- **Sesiones propias** en lugar de Flask-Session: evita la dependencia
  `msgspec` en Python 3.14 y deja el uso de Redis explícito en el código.
- **Cache-aside con TTL corto** para búsquedas e invalidación explícita de
  fichas al importar o al modificar la biblioteca.
- **Contadores sincronizados**: `cnt:likes` se recalcula desde MongoDB en cada
  alta/edición/borrado de una entrada, de modo que el contador no se desvía.
- **Ranking por visitas**: cada `GET /titles/<id>` hace `INCR` y `ZINCRBY`.

## Pruebas

Las pruebas usan la base 15 de Redis (`redis://localhost:6379/15`) y hacen
`flushdb` en cada fixture. La suite completa son 121 pruebas:

```powershell
python -m pytest tests/test_auth_session.py tests/test_cache.py tests/test_cache_routes.py -q
```

# Redis en la biblioteca virtual

Redis cumple funciones críticas de alto rendimiento dentro del sistema:

1. **Sesiones dinámicas** (`sess:<sid>`), con cookie `sid` `HttpOnly` y **TTL diferenciado**:
   - `admin`: Sesión extendida de 7 días.
   - `user`: Sesión de **30 minutos por inactividad** con renovación automática (*Sliding Window* al navegar).
2. **Historial de visualización** (`recent:views:<user_id>`), usando la estructura nativa **`LIST`** (`LPUSH`, `LREM`, `LTRIM`).
3. **Usuarios activos en tiempo real** (`online:active`), un **`ZSET`** ordenado por timestamp para conocer en todo momento la concurrencia exacta en los últimos 5 minutos (`ZREMRANGEBYSCORE`, `ZCARD`).
4. **Protección anti-spam y Rate Limiting** (`ratelimit:search:<ip>`), usando **`STRING` + `INCR` + `EXPIRE`** para limitar a 40 búsquedas por minuto.
5. **Cache-aside** de búsquedas y fichas (`cache:*`).
6. **Contadores atómicos** de visitas y favoritos (`cnt:*`).
7. **Rankings duales en Sorted Sets**:
   - `rank:popular`: ZSET de títulos ordenados por visitas acumuladas.
   - `rank:favorites`: ZSET de títulos con más favoritos de la comunidad.

La implementación vive en `app/auth/session.py` y `app/cache.py`.

## Mapa de claves completo

| Clave | Estructura | Contenido | TTL / Política |
| :--- | :--- | :--- | :--- |
| `sess:<sid>` | **`HASH`** | `user_id` y `role` de la sesión | Admin: 7 días \| User: 30 min (*Sliding TTL*) |
| `recent:views:<uid>` | **`LIST`** | Últimos 6 títulos vistos por el usuario | FIFO (`LPUSH` + `LTRIM 0 5`) |
| `online:active` | **`ZSET`** | Identificador de usuario → timestamp | Ventana móvil de 5 min (`ZREMRANGEBYSCORE`) |
| `ratelimit:search:<ip>` | **`STRING`** | Contador de búsquedas por IP | 60 segundos (`INCR` + `EXPIRE`) |
| `cache:search:<db>:<hash>` | **`STRING`** | JSON con resultados de búsqueda | 60 s |
| `cache:title:<db>:<id>` | **`STRING`** | Ficha serializada + promedio de notas | 300 s |
| `cache:api:<db>:<hash>` | **`STRING`** | Resultados externos (Jikan/TMDB) | 600 s |
| `cnt:views:<id>` | **`STRING`** | Contador de visitas acumuladas | Atómico (`INCR`) |
| `cnt:likes:<id>` | **`STRING`** | Total de favoritos de la comunidad | Sincronizado con MongoDB |
| `rank:popular` | **`ZSET`** | Título → Visitas acumuladas | Permanente |
| `rank:favorites` | **`ZSET`** | Título → Total de favoritos | Permanente |

## Comandos útiles para verificar en consola

```powershell
# Comprobar estado de Redis
redis-cli ping

# Ver sesiones y TTL restante
redis-cli keys "sess:*"
redis-cli ttl "sess:<sid>"
redis-cli hgetall "sess:<sid>"

# Ver historial de vistos recientemente de un usuario (LIST)
redis-cli lrange "recent:views:<user_id>" 0 -1

# Ver usuarios activos en tiempo real (ZSET)
redis-cli zrange "online:active" 0 -1 withscores
redis-cli zcard "online:active"

# Ver los 5 títulos más populares (ZSET)
redis-cli zrevrange "rank:popular" 0 4 withscores

# Ver los títulos con más favoritos (ZSET)
redis-cli zrevrange "rank:favorites" 0 4 withscores

# Ver claves en caché
redis-cli --scan --pattern "cache:*"
```

## Pruebas de Redis

Las pruebas corren sobre la base 15 de Redis (`redis://localhost:6379/15`):
```powershell
.\.venv\Scripts\python -m pytest tests/test_auth_session.py tests/test_cache.py -q
```

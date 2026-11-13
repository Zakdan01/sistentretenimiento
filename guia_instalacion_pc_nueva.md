# Guía Rápida de Despliegue en una PC Nueva

Esta guía asume que tienes una máquina nueva donde acabas de copiar/clonar la carpeta del proyecto y que ya cuenta con los servicios de **MongoDB** y **Redis** instalados.

---

## Requisitos Previos

Asegúrate de contar con lo siguiente en la máquina:
1. **Python 3.12+** instalado con la opción *"Add Python to PATH"* marcada.
2. **MongoDB** corriendo en segundo plano (`localhost:27017`).
3. **Redis** corriendo en segundo plano (`localhost:6379`).
4. **`mongosh`** (MongoDB Shell) instalado y disponible en la consola.

---

## Flujo de Despliegue en 6 Pasos

Abre una consola de **PowerShell** en la carpeta raíz del proyecto:
```powershell
cd "D:\Semestre_2_2026\Base de datos 3\caso de estudio 2"
```

### Paso 1: Crear el entorno virtual de Python
Crea un entorno aislado para evitar conflictos con otras versiones de librerías:
```powershell
python -m venv .venv
```

### Paso 2: Instalar las dependencias del proyecto
Instala Flask, PyMongo, Redis-py y las demás librerías requeridas:
```powershell
.\.venv\Scripts\pip install -r requirements.txt
```

### Paso 3: Configurar las variables de entorno
Copia la plantilla de configuración predeterminada:
```powershell
Copy-Item .env.example .env
```
*(Opcional: Si deseas que la base se llame `sistemaentretenimiento` en vez de `catalogo`, abre el archivo `.env` y ajusta `MONGO_DB=sistemaentretenimiento`).*

### Paso 4: Inicializar colecciones e índices en MongoDB
Ejecuta los dos scripts de inicialización que crean las colecciones con validadores estrictos y los índices de búsqueda:
```powershell
mongosh "mongodb://localhost:27017/sistemaentretenimiento" --quiet --file mongodb/init/01_collections.js
mongosh "mongodb://localhost:27017/sistemaentretenimiento" --quiet --file mongodb/init/02_indexes.js
```

### Paso 5: Cargar los datos iniciales (Seed)
Ejecuta el script que carga los 1,500 títulos (películas, series y animes), los 3 usuarios demo y las 18 entradas de biblioteca:
```powershell
.\.venv\Scripts\python -m mongodb.seed.load_seed --reset
```

### Paso 6: Iniciar la aplicación web
Arranca el servidor de desarrollo de Flask:
```powershell
.\.venv\Scripts\python -m flask --app app.run run
```

---

## Verificación y Acceso

1. Abre tu navegador web e ingresa a:  
   👉 **`http://127.0.0.1:5000`**
2. Cuentas demo para probar:
   - **Administrador**: `admin@biblioteca.local` / `Admin12345`
   - **Usuario**: `laura@biblioteca.local` / `Laura12345`
3. Comprobación de salud del servidor:  
   👉 `http://127.0.0.1:5000/health` (debe devolver `{"status": "ok"}`).

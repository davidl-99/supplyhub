# SupplyHub

SupplyHub es una plataforma B2B donde empresas proveedoras pueden administrar sus productos e inventario, mientras empresas compradoras pueden buscar productos y crear pedidos.

## Estado del proyecto

El proyecto se encuentra actualmente en su etapa inicial de planificación y definición de arquitectura.

## Problema

Muchas empresas necesitan administrar catálogos, existencias y pedidos entre organizaciones.

Una tienda online tradicional normalmente está pensada para compradores individuales. SupplyHub estará orientado a relaciones entre empresas, donde pueden existir:

* Diferentes organizaciones.
* Diferentes empleados dentro de cada organización.
* Roles y permisos.
* Múltiples almacenes.
* Precios específicos para determinados clientes.
* Reservas de inventario.
* Auditoría de operaciones.
* Búsquedas avanzadas de productos.

## Objetivo

El objetivo de este proyecto es construir una aplicación profesional que permita demostrar conocimientos de:

* Desarrollo frontend.
* Desarrollo backend.
* Diseño de APIs.
* Arquitectura de software.
* Bases de datos relacionales.
* Bases de datos documentales.
* Motores de búsqueda.
* Pruebas automatizadas.
* Docker.
* Integración y despliegue continuo.
* Documentación técnica.

## Tipos de usuario

### Administrador de plataforma

Administra el funcionamiento general de SupplyHub.

### Administrador de organización

Administra los usuarios, roles y configuraciones de una empresa.

### Gestor de catálogo

Crea, modifica y desactiva productos.

### Operador de almacén

Administra existencias y movimientos de inventario.

### Comprador

Busca productos y crea pedidos.

### Usuario de consulta

Puede consultar información, pero no puede modificarla.

## Funcionalidades del MVP

La primera versión funcional incluirá:

* Creación de organizaciones.
* Administración de usuarios.
* Administración de roles y permisos.
* Creación y modificación de productos.
* Administración de almacenes.
* Administración de inventario.
* Búsqueda de productos.
* Creación de pedidos.
* Consulta del estado de los pedidos.
* Registro de operaciones importantes.

## Funcionalidades fuera del MVP

Las siguientes funcionalidades no se desarrollarán inicialmente:

* Pagos reales.
* Facturación electrónica.
* Aplicación móvil.
* Recomendaciones con inteligencia artificial.
* Kubernetes.
* Microservicios.
* Microfrontends.
* Múltiples lenguajes backend.
* Integraciones con empresas de transporte.

Estas funcionalidades podrán evaluarse después de completar una primera versión estable.

## Arquitectura inicial

El proyecto comenzará utilizando un monolito modular.

Esto significa que existirá una sola aplicación backend, pero estará dividida internamente en módulos independientes.

Los módulos iniciales serán:

* Autenticación.
* Organizaciones.
* Usuarios y permisos.
* Catálogo.
* Inventario.
* Pedidos.
* Búsqueda.
* Auditoría.

No se utilizarán microservicios al comienzo porque primero es necesario comprender y completar correctamente las reglas de negocio dentro de una aplicación más sencilla de desarrollar y ejecutar.

## Tecnologías planificadas

### Frontend

* React.
* TypeScript.

### Backend

* Python.
* FastAPI.
* SQLAlchemy.
* Alembic.
* Pydantic.
* Pytest.

### Almacenamiento

* PostgreSQL como fuente principal de información.
* MongoDB para eventos de auditoría.
* OpenSearch para búsqueda avanzada de productos.

### Infraestructura

* Docker.
* Docker Compose.
* GitHub Actions.

## Estrategia de almacenamiento

### PostgreSQL

PostgreSQL almacenará la información principal del negocio:

* Usuarios.
* Organizaciones.
* Productos.
* Almacenes.
* Inventario.
* Pedidos.
* Roles y permisos.

Será la fuente principal de verdad del sistema.

### MongoDB

MongoDB se utilizará para almacenar eventos de auditoría e historiales de operaciones.

Por ejemplo:

* Quién modificó un producto.
* Qué información cambió.
* Cuándo se realizó el cambio.
* Qué valores existían antes y después.

### OpenSearch

OpenSearch se utilizará para realizar búsquedas avanzadas de productos.

Permitirá implementar:

* Búsqueda por texto.
* Filtros por categoría.
* Filtros por marca.
* Rangos de precios.
* Filtros por atributos.
* Ordenamiento de resultados.

OpenSearch no será la fuente principal de información. Sus índices deberán poder reconstruirse utilizando los datos almacenados en PostgreSQL.

## Plan inicial

1. Definir el alcance del producto.
2. Preparar la estructura del repositorio.
3. Crear el entorno local con Docker.
4. Crear la aplicación backend.
5. Conectar PostgreSQL.
6. Implementar el módulo de productos.
7. Crear la aplicación frontend.
8. Implementar autenticación y organizaciones.
9. Implementar inventario.
10. Implementar pedidos.
11. Integrar OpenSearch.
12. Integrar MongoDB.
13. Añadir procesamiento asíncrono.
14. Añadir pruebas automatizadas.
15. Configurar integración y despliegue continuo.

## Principios del proyecto

* La complejidad debe añadirse únicamente cuando resuelva un problema real.
* Cada funcionalidad debe estar documentada.
* Las reglas de negocio deben tener pruebas automatizadas.
* PostgreSQL será la fuente principal de verdad.
* Los errores deben manejarse de manera explícita.
* La arquitectura debe facilitar el mantenimiento.
* Las herramientas de inteligencia artificial serán asistentes, no sustitutos de la comprensión técnica.

## Autor

Proyecto desarrollado como parte de un proceso de aprendizaje y fortalecimiento profesional en desarrollo full stack y arquitectura de software.

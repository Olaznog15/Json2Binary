# Json2Class

Este proyecto inspecciona un archivo de estructura JSON y genera dinámicamente clases (dataclasses) nativas de Python que mapean y espejan dicho esquema. Además de definir las clases, genera métodos para instanciar y exportar objetos con fidelidad, permitiendo leer y crear nuevos JSONs usando programación orientada a objetos estricta.

## Características Principales

- **Validación de Identificadores Python**: No importa si las claves JSON contienen espacios, paréntesis, u otros caracteres no válidos. El generador las limpiará de manera segura:
  - Genera nombres para Clases en `PascalCase`.
  - Genera los nombres de atributos o campos en formato válido y usualmente en  `snake_case`.
- **Mapeo JSON-Python Integrado**: Para asegurar fidelidad total al esquema, el código generado inyecta de forma subyacente la función `@classmethod from_dict()` (para importar y mapear con claves de JSON) y `.to_dict()` (para exportar y mapear con las claves problemáticas nativas de vuelta a sus strings literales JSON originales).
- **Soporte Avanzado de Enumerados (ENUM)**: Si el proyecto detecta algún nodo especial con nombre literal de clave `"ENUM"`, procesará sus nodos hijos para convertirlos en identificadores reales utilizando los validadores formales y la herencia `enum.Enum` nativa de Python.

## Estructura del Proyecto

- `default.json` / `aeronautical.json` / `enum_test.json`: Archivos JSON de ejemplo preparados para testear sus distintas particularidades (tipología base, anidaciones complejas, y enumerados / nombres problemáticos respectivamente).
- `src/generator.py`: Script y núcleo del programa que parsea el JSON y genera las clases Python de forma dinámica.
- `src/main.py`: Script principal que ejecuta el generador y demuestra, instanciando clases generadas y exportándolas, cómo utilizar el código.
- `requirements.txt`: Lista de dependencias en caso de necesitar extensiones a futuro.

## Cómo Usar

1. Ejecuta el script principal (por defecto procesará el json incluido en su ruta relativa):
   ```bash
   python src/main.py
   ```
2. Esto generará las clases en `src/generated_class.py`. 
3. El propio `main.py` instanciará una de esas dataclasses, insertará información, y utilizará `to_dict()` generándote un nuevo archivo exportado en la carpeta de salida (por ejemplo `output/generated_aeronautical.json`).

## Requisitos

- Python 3.12+
- Entorno virtual configurado en `.venv`

import PyInstaller.__main__
import os
import shutil
import time

# Intentar eliminar las carpetas previas de compilación de forma segura
for folder in ['build', 'dist']:
    if os.path.exists(folder):
        try:
            shutil.rmtree(folder)
            print(f"Carpeta anterior '{folder}' limpiada con éxito.")
        except Exception as e:
            print(f"Aviso: No se pudo eliminar '{folder}' (está bloqueada por OneDrive o un proceso). Intentando continuar...")

time.sleep(1)

html_file = os.path.abspath("index.html")

# Ejecutar PyInstaller sin el parámetro --clean automático para evitar bloqueos
PyInstaller.__main__.run([
    'main.py',                        
    '--name=MarketDesktopApp',        
    '--onefile',                      
    '--noconsole',                    
    f'--add-data={html_file};.',      
])

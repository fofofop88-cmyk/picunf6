import sys
import os

# Добавляем путь к проекту
path = '/home/gandon/1'
if path not in sys.path:
    sys.path.append(path)

# Импортируем приложение
from app import app as application

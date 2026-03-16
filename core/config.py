import os

class ConfigManager:
    """Класс для работы с конфигурационными файлами в формате Bash (.conf)"""
    
    @staticmethod
    def load(file_path):
        """Загружает конфиг из файла"""
        if not os.path.exists(file_path):
            return {}
        
        config = {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Пропускаем пустые строки и комментарии
                    if not line or line.startswith('#'):
                        continue
                    
                    if '=' in line:
                        key, val = line.split('=', 1)
                        key = key.strip()
                        # Убираем кавычки вокруг значения
                        val = val.strip().strip("'").strip('"')
                        config[key] = val
        except Exception as e:
            from .utils import warn
            warn(f"Ошибка при чтении {file_path}: {e}")
            
        return config

    @staticmethod
    def save(file_path, data):
        """Сохраняет конфиг в файл в формате Bash"""
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                for key, val in data.items():
                    # Сохраняем значения в одинарных кавычках для совместимости
                    f.write(f"{key}='{val}'\n")
            return True
        except Exception as e:
            from .utils import err
            err(f"Ошибка при записи {file_path}: {e}")
            return False

    @staticmethod
    def delete(file_path):
        """Удаляет файл конфигурации"""
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                return True
            except Exception as e:
                from .utils import err
                err(f"Ошибка при удалении {file_path}: {e}")
        return False

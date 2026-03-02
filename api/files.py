"""
API модуль для работы с файлами и папками.
"""
import os
import shutil
import json
from typing import Dict, Any, Optional
from pathlib import Path


class FilesAPI:
    """API для операций с файлами и папками."""
    
    @staticmethod
    def create_file(filepath: str, content: str = "") -> Dict[str, Any]:
        """
        Создает файл.
        
        Args:
            filepath: Путь к файлу
            content: Содержимое файла
            
        Returns:
            Результат операции
        """
        try:
            # Создаем директорию если не существует (только если есть поддиректории)
            dir_path = os.path.dirname(filepath)
            if dir_path:  # Проверяем, что путь не пустой (для корневых файлов dir_path будет '')
                os.makedirs(dir_path, exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return {
                "success": True,
                "message": f"File {filepath} created successfully",
                "filepath": filepath
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error creating file {filepath}: {str(e)}",
                "filepath": filepath
            }
    
    @staticmethod
    def delete_file(filepath: str) -> Dict[str, Any]:
        """
        Удаляет файл.
        
        Args:
            filepath: Путь к файлу
            
        Returns:
            Результат операции
        """
        try:
            if os.path.exists(filepath):
                if os.path.isfile(filepath):
                    os.remove(filepath)
                else:
                    shutil.rmtree(filepath)
                
                return {
                    "success": True,
                    "message": f"{filepath} deleted successfully",
                    "filepath": filepath
                }
            else:
                return {
                    "success": False,
                    "message": f"File {filepath} not found",
                    "filepath": filepath
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error deleting {filepath}: {str(e)}",
                "filepath": filepath
            }
    
    @staticmethod
    def create_directory(dirpath: str) -> Dict[str, Any]:
        """
        Создает директорию.
        
        Args:
            dirpath: Путь к директории
            
        Returns:
            Результат операции
        """
        try:
            os.makedirs(dirpath, exist_ok=True)
            return {
                "success": True,
                "message": f"Directory {dirpath} created successfully",
                "dirpath": dirpath
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error creating directory {dirpath}: {str(e)}",
                "dirpath": dirpath
            }
    
    @staticmethod
    def delete_directory(dirpath: str) -> Dict[str, Any]:
        """
        Удаляет директорию.
        
        Args:
            dirpath: Путь к директории
            
        Returns:
            Результат операции
        """
        try:
            if os.path.exists(dirpath):
                shutil.rmtree(dirpath)
                return {
                    "success": True,
                    "message": f"Directory {dirpath} deleted successfully",
                    "dirpath": dirpath
                }
            else:
                return {
                    "success": False,
                    "message": f"Directory {dirpath} not found",
                    "dirpath": dirpath
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error deleting directory {dirpath}: {str(e)}",
                "dirpath": dirpath
            }
    
    @staticmethod
    def read_file(filepath: str) -> Dict[str, Any]:
        """
        Читает содержимое файла.
        
        Args:
            filepath: Путь к файлу
            
        Returns:
            Результат с содержимым файла
        """
        try:
            if os.path.exists(filepath) and os.path.isfile(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                return {
                    "success": True,
                    "content": content,
                    "filepath": filepath
                }
            else:
                return {
                    "success": False,
                    "message": f"File {filepath} not found",
                    "filepath": filepath
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error reading file {filepath}: {str(e)}",
                "filepath": filepath
            }
    
    @staticmethod
    def write_file(filepath: str, content: str) -> Dict[str, Any]:
        """
        Записывает содержимое в файл.
        
        Args:
            filepath: Путь к файлу
            content: Содержимое для записи
            
        Returns:
            Результат операции
        """
        try:
            # Создаем директорию если не существует (только если есть поддиректории)
            dir_path = os.path.dirname(filepath)
            if dir_path:  # Проверяем, что путь не пустой (для корневых файлов dir_path будет '')
                os.makedirs(dir_path, exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return {
                "success": True,
                "message": f"File {filepath} written successfully",
                "filepath": filepath
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error writing file {filepath}: {str(e)}",
                "filepath": filepath
            }
    
    @staticmethod
    def get_file_info(filepath: str) -> Dict[str, Any]:
        """
        Получает информацию о файле.
        
        Args:
            filepath: Путь к файлу
            
        Returns:
            Информация о файле
        """
        try:
            if os.path.exists(filepath):
                stat = os.stat(filepath)
                return {
                    "success": True,
                    "filepath": filepath,
                    "size": stat.st_size,
                    "is_file": os.path.isfile(filepath),
                    "is_dir": os.path.isdir(filepath),
                    "modified": stat.st_mtime
                }
            else:
                return {
                    "success": False,
                    "message": f"File {filepath} not found",
                    "filepath": filepath
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error getting file info {filepath}: {str(e)}",
                "filepath": filepath
            }
    
    @staticmethod
    def rename_file(old_path: str, new_path: str) -> Dict[str, Any]:
        """
        Переименовывает файл или директорию.
        
        Args:
            old_path: Старый путь
            new_path: Новый путь
            
        Returns:
            Результат операции
        """
        try:
            if not os.path.exists(old_path):
                return {
                    "success": False,
                    "message": f"File or directory {old_path} not found",
                    "old_path": old_path,
                    "new_path": new_path
                }
            
            if os.path.exists(new_path):
                return {
                    "success": False,
                    "message": f"File or directory {new_path} already exists",
                    "old_path": old_path,
                    "new_path": new_path
                }
            
            os.rename(old_path, new_path)
            
            return {
                "success": True,
                "message": f"Renamed {old_path} to {new_path}",
                "old_path": old_path,
                "new_path": new_path
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error renaming {old_path} to {new_path}: {str(e)}",
                "old_path": old_path,
                "new_path": new_path
            }
    
    @staticmethod
    def list_directory(dirpath: str) -> Dict[str, Any]:
        """
        Списывает содержимое директории.
        
        Args:
            dirpath: Путь к директории
            
        Returns:
            Список файлов и папок
        """
        try:
            if os.path.exists(dirpath) and os.path.isdir(dirpath):
                items = []
                for item in os.listdir(dirpath):
                    item_path = os.path.join(dirpath, item)
                    items.append({
                        "name": item,
                        "path": item_path,
                        "is_file": os.path.isfile(item_path),
                        "is_dir": os.path.isdir(item_path)
                    })
                
                return {
                    "success": True,
                    "dirpath": dirpath,
                    "items": items
                }
            else:
                return {
                    "success": False,
                    "message": f"Directory {dirpath} not found",
                    "dirpath": dirpath
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error listing directory {dirpath}: {str(e)}",
                "dirpath": dirpath
            }

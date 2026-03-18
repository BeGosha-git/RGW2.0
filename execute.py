"""
Модуль для выполнения команд и исполняемых файлов в терминале Ubuntu.
Поддерживает логирование и симуляцию ввода с клавиатуры.
"""
import subprocess
import sys
import os
import threading
import queue
import time
from typing import Optional, Callable, List


class CommandExecutor:
    """Класс для выполнения команд с поддержкой логирования и симуляции ввода."""
    
    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        """
        Инициализация исполнителя команд.
        
        Args:
            log_callback: Функция для обработки логов (stdout/stderr)
        """
        self.log_callback = log_callback
        self.process: Optional[subprocess.Popen] = None
        self.stdin_lock = threading.Lock()
    
    def execute(self, command: str, args: List[str] = None, 
                working_dir: Optional[str] = None, 
                input_data: Optional[str] = None,
                shell: bool = False,
                keep_stdin_open: bool = False) -> int:
        """
        Выполняет команду в терминале скрыто с поддержкой логирования.
        
        Args:
            command: Команда или путь к исполняемому файлу
            args: Список аргументов команды
            working_dir: Рабочая директория
            input_data: Начальные данные для ввода в процесс (если keep_stdin_open=False, stdin закроется после отправки)
            shell: Использовать shell для выполнения
            keep_stdin_open: Оставить stdin открытым для последующей симуляции ввода
            
        Returns:
            Код возврата процесса
        """
        if args is None:
            args = []
        
        cmd_list = [command] + args if not shell else command
        
        try:
            self.process = subprocess.Popen(
                cmd_list if not shell else command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=working_dir,
                shell=shell
            )
            
            # Потоки для чтения stdout и stderr
            stdout_queue = queue.Queue()
            stderr_queue = queue.Queue()
            
            def read_output(pipe, q):
                """Читает вывод из pipe и помещает в очередь."""
                try:
                    for line in iter(pipe.readline, ''):
                        if line:
                            q.put(('stdout', line))
                    pipe.close()
                except Exception as e:
                    q.put(('error', str(e)))
            
            def read_error(pipe, q):
                """Читает ошибки из pipe и помещает в очередь."""
                try:
                    for line in iter(pipe.readline, ''):
                        if line:
                            q.put(('stderr', line))
                    pipe.close()
                except Exception as e:
                    q.put(('error', str(e)))
            
            # Запуск потоков для чтения
            stdout_thread = threading.Thread(
                target=read_output, 
                args=(self.process.stdout, stdout_queue),
                daemon=True
            )
            stderr_thread = threading.Thread(
                target=read_error,
                args=(self.process.stderr, stderr_queue),
                daemon=True
            )
            
            stdout_thread.start()
            stderr_thread.start()
            
            # Отправка начальных входных данных если есть
            if input_data and self.process.stdin:
                with self.stdin_lock:
                    if self.process.stdin:
                        self.process.stdin.write(input_data)
                        self.process.stdin.flush()
                        if not keep_stdin_open:
                            self.process.stdin.close()
            elif not keep_stdin_open and self.process.stdin:
                with self.stdin_lock:
                    if self.process.stdin:
                        self.process.stdin.close()
            
            # Обработка вывода в реальном времени
            while self.process.poll() is None or not (stdout_queue.empty() and stderr_queue.empty()):
                try:
                    # Проверка stdout
                    while not stdout_queue.empty():
                        source, line = stdout_queue.get_nowait()
                        if self.log_callback:
                            self.log_callback(line.rstrip())
                    
                    # Проверка stderr
                    while not stderr_queue.empty():
                        source, line = stderr_queue.get_nowait()
                        if self.log_callback:
                            self.log_callback(f"ERROR: {line.rstrip()}")
                    
                    # Небольшая задержка чтобы не нагружать CPU
                    time.sleep(0.1)
                except queue.Empty:
                    pass
            
            # Закрываем stdin если он еще открыт
            if keep_stdin_open and self.process.stdin:
                with self.stdin_lock:
                    if self.process.stdin:
                        self.process.stdin.close()
            
            # Ожидание завершения потоков чтения перед финальным дрейном
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)

            # Финальный дрейн очередей — данные, записанные после выхода из цикла
            while not stdout_queue.empty():
                _, line = stdout_queue.get_nowait()
                if self.log_callback:
                    self.log_callback(line.rstrip())
            while not stderr_queue.empty():
                _, line = stderr_queue.get_nowait()
                if self.log_callback:
                    self.log_callback(f"ERROR: {line.rstrip()}")

            return self.process.returncode if self.process.returncode is not None else 0
            
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"Execution error: {str(e)}")
            return -1
    
    def send_input(self, data: str) -> bool:
        """
        Симулирует ввод с клавиатуры, отправляя данные в stdin процесса.
        
        Args:
            data: Данные для отправки в процесс
            
        Returns:
            True если успешно отправлено, False если процесс завершен или stdin закрыт
        """
        if not self.process or self.process.poll() is not None:
            return False
        
        with self.stdin_lock:
            if not self.process.stdin:
                return False
            
            try:
                self.process.stdin.write(data)
                self.process.stdin.flush()
                return True
            except (BrokenPipeError, OSError):
                return False
    
    def send_input_line(self, line: str) -> bool:
        """
        Симулирует ввод строки с клавиатуры (добавляет перенос строки).
        
        Args:
            line: Строка для отправки
            
        Returns:
            True если успешно отправлено
        """
        return self.send_input(line + '\n')
    
    def stop(self):
        """Останавливает выполняющийся процесс."""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


def execute_command(command: str, args: List[str] = None, 
                   working_dir: Optional[str] = None,
                   log_callback: Optional[Callable[[str], None]] = None) -> int:
    """
    Удобная функция для выполнения команды.
    
    Args:
        command: Команда для выполнения
        args: Аргументы команды
        working_dir: Рабочая директория
        log_callback: Функция для обработки логов
        
    Returns:
        Код возврата процесса
    """
    executor = CommandExecutor(log_callback)
    return executor.execute(command, args, working_dir)

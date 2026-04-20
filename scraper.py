import sqlite3
import json
import logging
import random
import time
from typing import Dict, Optional, Generator

from youtube_comment_downloader import (
    YoutubeCommentDownloader,
    SORT_BY_RECENT,
    SORT_BY_POPULAR
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RobustYoutubeScraper:
    def __init__(self, db_path: str, proxy_list: list = None):
        self.db_path = db_path
        self.proxy_list = proxy_list or []
        self.init_db()

    def init_db(self):
        """Создаёт таблицы, если их нет."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA_SQL)

    def get_session_with_proxy(self) -> YoutubeCommentDownloader:
        """Создаёт загрузчик со случайным прокси."""
        downloader = YoutubeCommentDownloader()
        if self.proxy_list:
            proxy = random.choice(self.proxy_list)
            # Формат прокси: {'http': 'http://user:pass@ip:port', 'https': 'https://user:pass@ip:port'}
            downloader.session.proxies.update(proxy)
            logger.info(f"Используется прокси: {proxy.get('http', proxy.get('https'))}")
        return downloader

    def _patch_downloader(self, downloader: YoutubeCommentDownloader, video_id: str):
        """
        Внедряет MITM-хуки для перехвата continuation-токенов.
        Это позволяет возобновлять парсинг с того же места.
        """
        original_ajax = downloader.ajax_request
        def patched_ajax_request(endpoint, ytcfg, retries=5, sleep=20, timeout=60):
            # Вызываем оригинальный метод
            response = original_ajax(endpoint, ytcfg, retries, sleep, timeout)
            if response:
                # Сохраняем токен, если он есть в ответе
                token = self.extract_continuation_token(response)
                if token:
                    self.save_continuation_token(video_id, token)
            return response
        downloader.ajax_request = patched_ajax_request.__get__(downloader)
        return downloader

    def extract_continuation_token(self, response: dict) -> Optional[str]:
        """Извлекает continuation token из ответа API."""
        # Логика извлечения зависит от структуры ответа, может быть в response.get('continuation')
        # Реализация требует анализа конкретных ответов от YouTube.
        # В общем случае ищем ключи 'continuation', 'token', 'ctoken'
        if 'continuationContents' in response:
            # типичная структура для YouTube API
            return response.get('continuationContents', {}).get('continuationToken')
        return None

    def save_continuation_token(self, video_id: str, token: str):
        """Сохраняет токен пагинации для видео."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO continuations (video_id, continuation_token)
                VALUES (?, ?)
            """, (video_id, token))
            # Обновляем статус видео, чтобы знать, что есть сохранённый прогресс
            conn.execute("""
                UPDATE videos SET status = 'in_progress', last_comment_id = ?
                WHERE video_id = ?
            """, (token, video_id))

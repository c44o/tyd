import asyncio
from playwright.async_api import async_playwright
import sqlite3
import time


DB_PATH = 'comments.db'

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS comments (
                id TEXT PRIMARY KEY,
                video_id TEXT,
                author TEXT,
                text TEXT,
                likes INTEGER,
                time TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

async def main():
    init_db()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # видимый браузер
        context = await browser.new_context()
        page = await context.new_page()
        
        video_url = input("Введите URL видео: ")
        await page.goto(video_url)
        await page.wait_for_timeout(5000)  # подождать загрузки
        
        print("Теперь вручную прокручивайте страницу и разворачивайте ветки. Нажмите Ctrl+C для завершения.")
        
        collected_ids = set()
        try:
            while True:
                # Разворачиваем все кнопки "Показать ответы"
                await page.evaluate('''
                    document.querySelectorAll('#more-replies, tp-yt-paper-button#button[aria-label*="ответов"]')
                        .forEach(btn => btn.click());
                ''')
                # Собираем комментарии
                comments = await page.evaluate('''
                    () => {
                        const items = [];
                        document.querySelectorAll('#comment-section ytd-comment-thread-renderer').forEach(el => {
                            const id = el.id || Math.random().toString();
                            const author = el.querySelector('#author-text')?.innerText.trim() || '';
                            const text = el.querySelector('#content-text')?.innerText.trim() || '';
                            const likes = parseInt(el.querySelector('#vote-count-middle')?.innerText) || 0;
                            const time = el.querySelector('#published-time-text a')?.innerText || '';
                            items.push({id, author, text, likes, time});
                        });
                        return items;
                    }
                ''')
                # Сохраняем новые
                with sqlite3.connect(DB_PATH) as conn:
                    for c in comments:
                        if c['id'] not in collected_ids:
                            collected_ids.add(c['id'])
                            conn.execute(
                                "INSERT OR IGNORE INTO comments (id, video_id, author, text, likes, time) VALUES (?, ?, ?, ?, ?, ?)",
                                (c['id'], video_url.split('v=')[-1], c['author'], c['text'], c['likes'], c['time'])
                            )
                print(f"Собрано уникальных комментариев: {len(collected_ids)}")
                await asyncio.sleep(3)  # пауза между сборами
        except KeyboardInterrupt:
            print("Завершение работы...")
        finally:
            await browser.close()

if __name__ == '__main__':
    asyncio.run(main())

import os
import re
import json
import aiohttp
import logging
import asyncio
from datetime import datetime
from bs4 import BeautifulSoup
from telethon import TelegramClient, events
from functools import lru_cache
from PIL import Image
from io import BytesIO

# ====== CONFIG ======
CONFIG_FILE = 'bot_config.json'

def load_config():
    """Load configuration from file or create new one if not exists"""
    default_config = {
        'api_id': None,
        'api_hash': None,
        'target_group': None
    }
    
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return default_config.copy()

def save_config(config):
    """Save configuration to file"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def setup_config():
    """Interactive configuration setup"""
    config = load_config()
    
    print("=== Pinterest Bot Configuration ===")
    print("Press Enter to keep current value (shown in brackets)")
    
    # Get API ID
    current_api_id = config.get('api_id', 'Not set')
    api_id = input(f"Enter Telegram API ID [{current_api_id}]: ").strip()
    if api_id:
        config['api_id'] = int(api_id)
    elif config['api_id'] is None:
        raise ValueError("API ID is required for first setup")

    # Get API Hash
    current_api_hash = config.get('api_hash', 'Not set')
    api_hash = input(f"Enter Telegram API Hash [{current_api_hash}]: ").strip()
    if api_hash:
        config['api_hash'] = api_hash
    elif config['api_hash'] is None:
        raise ValueError("API Hash is required for first setup")

    # Get Target Group
    current_target = config.get('target_group', 'Not set')
    target_group = input(f"Enter Target Group ID [{current_target}]: ").strip()
    if target_group:
        config['target_group'] = int(target_group)
    elif config['target_group'] is None:
        raise ValueError("Target Group ID is required for first setup")

    # Save the configuration
    save_config(config)
    print("Configuration saved successfully!")
    return config

def get_config():
    """Get configuration, run setup if no config exists"""
    try:
        config = load_config()
        if None in config.values():
            config = setup_config()
        return config
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return setup_config()

# Load configuration
config = get_config()
api_id = config['api_id']
api_hash = config['api_hash']
target_group = config['target_group']

# ====== TELETHON SETUP ======
client = TelegramClient('session', api_id, api_hash)
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# ====== SESSION SETUP ======
session = None

async def get_session():
    global session
    if session is None:
        session = aiohttp.ClientSession()
    return session

def log(msg):
    print(f'[🌀] {msg}')

# ====== DOWNLOAD FUNCTION ======
async def download_file(url, filename, max_retries=3):
    log(f'⬇️ Đang tải: {url}')
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            session = await get_session()
            async with session.get(url) as response:
                response.raise_for_status()
                if url.endswith('.jpg') or url.endswith('.png'):
                    # Optimize image
                    data = await response.read()
                    img = Image.open(BytesIO(data))
                    
                    # Maintain quality while reducing file size
                    img = img.convert('RGB')
                    img.save(filename, 'JPEG', quality=85, optimize=True)
                else:
                    # For videos and other files
                    with open(filename, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
            return True
            
        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                wait_time = 2 ** retry_count  # Exponential backoff
                log(f'Lỗi tải file (lần {retry_count}): {e}. Thử lại sau {wait_time}s...')
                await asyncio.sleep(wait_time)
            else:
                log(f'Lỗi tải file sau {max_retries} lần thử: {e}')
                return False

# ====== PINTEREST EXTRACTOR ======
@lru_cache(maxsize=100)
async def extract_pinterest_media(pin_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    session = await get_session()
    log(f'➡ Chuyển về link gốc: {pin_url}')

    try:
        if 'pin.it' in pin_url:
            async with session.get(pin_url, headers=headers) as response:
                if response.status == 200:
                    content = await response.text()
                    soup = BeautifulSoup(content, "html.parser")
                    meta = soup.find("link", rel="alternate")
                    if meta and 'url=' in meta['href']:
                        match = re.search(r'url=(.*?)&', meta['href'])
                        if match:
                            pin_url = match.group(1)
                            log(f'➡ Link gốc: {pin_url}')

        async with session.get(pin_url, headers=headers) as response:
            if response.status != 200:
                return None, None
            content = await response.text()
            soup = BeautifulSoup(content, 'html.parser')

            # Tìm video với chất lượng cao nhất
            video_tag = soup.find("video")
            if video_tag and 'src' in video_tag.attrs:
                video_url = video_tag['src']
                # Ưu tiên chất lượng video cao nhất có sẵn
                qualities = ['1080p', '720p', '480p', '360p']
                for quality in qualities:
                    mp4_url = video_url.replace('/hls/', f'/{quality}/').replace('.m3u8', '.mp4')
                    try:
                        async with session.head(mp4_url) as vid_response:
                            if vid_response.status == 200:
                                return 'video', mp4_url
                    except:
                        continue

            # Tìm ảnh với chất lượng cao nhất
            img_sources = []
            # Kiểm tra meta og:image trước
            og_img = soup.find("meta", property="og:image")
            if og_img and 'content' in og_img.attrs:
                img_sources.append(og_img['content'])

            # Tìm tất cả thẻ img
            for img in soup.find_all("img"):
                if 'src' in img.attrs:
                    img_sources.append(img['src'])

            # Chọn ảnh có độ phân giải cao nhất
            best_image = None
            max_resolution = 0
            for img_url in img_sources:
                try:
                    if 'originals' in img_url:
                        return 'image', img_url
                    res_match = re.search(r'(\d+)x(\d+)', img_url)
                    if res_match:
                        resolution = int(res_match.group(1)) * int(res_match.group(2))
                        if resolution > max_resolution:
                            max_resolution = resolution
                            best_image = img_url
                except:
                    continue

            if best_image:
                return 'image', best_image

    except Exception as e:
        log(f'Lỗi khi trích xuất media: {e}')
    
    return None, None

# ====== HANDLE ANY MESSAGE WITH PINTEREST LINK ======
@client.on(events.NewMessage)
async def handler(event):
    try:
        text = event.raw_text
        if 'pinterest.com' not in text and 'pin.it' not in text:
            return

        # Tìm tất cả các link Pinterest trong tin nhắn
        links = re.findall(r'(https?://(?:www\.)?(?:pinterest\.com/[^\s]+|pin\.it/[^\s]+))', text)
        if not links:
            return

        processed = []
        for link in links:
            try:
                log(f'Xử lý link: {link}')
                file_type, url = await extract_pinterest_media(link)

                if not url:
                    continue

                filename = datetime.now().strftime("%d%m%H%M%S") + f"_{len(processed)}"
                if file_type == 'video':
                    filename += '.mp4'
                elif file_type == 'image':
                    filename += '.jpg'

                if await download_file(url, filename):
                    processed.append(filename)
                else:
                    log(f'❌ Không thể tải: {url}')

            except Exception as e:
                log(f'Lỗi khi xử lý {link}: {e}')

        if processed:
            # Gửi tất cả file đã xử lý
            await client.send_file(target_group, processed)
            
            # Dọn dẹp file
            for filename in processed:
                try:
                    os.remove(filename)
                    log(f'🧹 Đã xoá file: {filename}')
                except Exception as e:
                    log(f'Lỗi khi xoá file {filename}: {e}')
        else:
            await event.reply("❌ Không tìm thấy ảnh hoặc video hợp lệ.")

    except Exception as e:
        await event.reply(f"❌ Đã xảy ra lỗi: {e}")
        log(f'Lỗi: {e}')

# ====== START BOT ======
with client:
    log("🤖 Bot đã chạy — chỉ cần gửi link Pinterest để tải ảnh/video.")
    client.run_until_disconnected()

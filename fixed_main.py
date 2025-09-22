# -*- coding: utf-8 -*-
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
import brotli  # Add Brotli import

# ====== CONFIG ======
CONFIG_FILE = 'bot_config.json'

def load_config():
    default_config = {
        'api_id': None,
        'api_hash': None
    }
    
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return default_config.copy()

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def setup_config():
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

    # Save the configuration
    save_config(config)
    print("Configuration saved successfully!")
    return config

def get_config():
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

# ====== LOGGING SETUP ======
def log(msg, end='\n'):
    print(f'[🌀] {msg}', end=end)

# ====== TELETHON SETUP ======
client = TelegramClient('session', api_id, api_hash)
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# ====== SESSION SETUP ======
session = None

async def get_session():
    global session
    if session is None:
        try:
            # Try to configure session with AsyncResolver
            connector = aiohttp.TCPConnector(
                resolver=aiohttp.AsyncResolver(),
                ssl=False,
                use_dns_cache=True
            )
            session = aiohttp.ClientSession(connector=connector)
        except Exception as e:
            log(f"⚠️ Không thể sử dụng AsyncResolver, dùng cấu hình mặc định: {e}")
            # Fallback to default configuration
            session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False)
            )
    return session

# ====== DOWNLOAD FUNCTION ======
async def download_file(url, filename, max_retries=3):
    log(f'⬇️ Đang tải: {url}')
    retry_count = 0
    chunk_size = 4 * 1024 * 1024  # 4MB chunks for faster download
    
    while retry_count < max_retries:
        try:
            session = await get_session()
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive'
            }
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                
                if url.endswith('.jpg') or url.endswith('.png') or url.endswith('.jpeg') or url.endswith('.webp'):
                    log('📥 Đang tải dữ liệu ảnh...')
                    data = await response.read()
                    img = Image.open(BytesIO(data))
                    
                    # Convert WEBP to JPEG if needed
                    if url.endswith('.webp'):
                        img = img.convert('RGB')
                    
                    width, height = img.size
                    log(f'📏 Kích thước gốc: {width}x{height}')
                    
                    # Calculate target size (4K or larger)
                    if max(width, height) < 3840:
                        scale = 3840 / max(width, height)
                        new_width = int(width * scale)
                        new_height = int(height * scale)
                        log(f'🔄 Nâng cấp ảnh lên {new_width}x{new_height}')
                        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    # Save with maximum quality
                    log('💾 Đang lưu ảnh chất lượng cao...')
                    img.save(filename, 'JPEG', quality=100, optimize=True, subsampling=0)
                    
                    log(f'✨ Đã lưu ảnh chất lượng cao: {filename}')
                else:
                    # For videos and other files
                    log('📥 Đang tải video/file...')
                    downloaded = 0
                    with open(filename, 'wb') as f:
                        async for chunk in response.content.iter_chunked(chunk_size):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size:
                                progress = (downloaded / total_size) * 100
                                log(f'\r📥 Tải xuống: {progress:.1f}% ({downloaded/1024/1024:.1f}/{total_size/1024/1024:.1f}MB)', end='')
                
                log(f'✅ Tải xuống hoàn tất: {filename}')
                return True
            
        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                wait_time = 2 ** retry_count  # Exponential backoff
                log(f'⚠️ Lỗi tải file (lần {retry_count}): {e}. Thử lại sau {wait_time}s...')
                await asyncio.sleep(wait_time)
            else:
                log(f'❌ Lỗi tải file sau {max_retries} lần thử: {e}')
                # Clean up partial file if it exists
                if os.path.exists(filename):
                    os.remove(filename)
                return False

# ====== PINTEREST EXTRACTOR ======
@lru_cache(maxsize=100)
async def extract_pinterest_media(pin_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Cookie': '_auth=1'
    }
    session = await get_session()
    log(f'➡ Đang xử lý link: {pin_url}')

    try:
        # Handle short links with retries
        if 'pin.it' in pin_url or '/i/' in pin_url:
            retry_count = 0
            max_retries = 3
            while retry_count < max_retries:
                try:
                    log(f'🔄 Đang giải quyết link ngắn (lần thử {retry_count + 1})...')
                    timeout = aiohttp.ClientTimeout(total=10)  # 10 seconds timeout
                    async with session.get(pin_url, headers=headers, allow_redirects=True, timeout=timeout) as response:
                        if response.status == 200:
                            # Get the final URL after redirects
                            final_url = str(response.url)
                            log(f'➡ Link gốc: {final_url}')
                            
                            # Try to find canonical URL from the page
                            content = await response.text()
                            soup = BeautifulSoup(content, "html.parser")
                            meta = soup.find("link", rel="canonical")
                            if meta and meta.get('href'):
                                final_url = meta['href']
                                log(f'➡ Link chính thức: {final_url}')
                            
                            # Update pin_url to the resolved URL if it's valid
                            if 'pinterest.com' in final_url:
                                pin_url = final_url
                                break
                            else:
                                log('⚠️ Link đích không phải Pinterest, thử lại...')
                        else:
                            log(f'⚠️ Lỗi HTTP {response.status}, thử lại...')
                    
                except asyncio.TimeoutError:
                    log('⚠️ Hết thời gian chờ, thử lại...')
                except Exception as e:
                    log(f'⚠️ Lỗi khi giải quyết link ngắn: {e}')
                
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count
                    log(f'⌛ Chờ {wait_time}s trước khi thử lại...')
                    await asyncio.sleep(wait_time)
                else:
                    log('❌ Không thể giải quyết link ngắn sau nhiều lần thử')

        async with session.get(pin_url, headers=headers) as response:
            if response.status != 200:
                return None, None
            content = await response.text()
            soup = BeautifulSoup(content, 'html.parser')

            # Kiểm tra xem có phải là video không
            is_video = False
            video_candidates = []
            
            # Phương pháp 1: Kiểm tra meta tags
            for meta in soup.find_all('meta', property=['og:type', 'og:video:type']):
                if 'video' in meta.get('content', '').lower():
                    is_video = True
                    break

            # Phương pháp 2: Kiểm tra thẻ video
            video_tag = soup.find("video")
            if video_tag:
                is_video = True
                log('🎥 Phát hiện video qua thẻ video...')

            # Phương pháp 3: Kiểm tra trong dữ liệu JSON
            for script in soup.find_all('script', type='text/javascript'):
                if 'videoList' in script.text or '"type":"video"' in script.text:
                    is_video = True
                    log('🎥 Phát hiện video qua dữ liệu JSON...')
                    break

            if is_video:
                log('🎥 Xác nhận đây là video Pinterest, đang quét tất cả nguồn...')
                
                # Thu thập nguồn video từ thẻ video
                if video_tag:
                    if 'src' in video_tag.attrs:
                        video_candidates.append(video_tag['src'])
                    
                    for source in video_tag.find_all('source'):
                        if source.get('src'):
                            video_candidates.append(source['src'])
                
                # Thu thập từ meta tags
                for meta in soup.find_all('meta', property=['og:video', 'og:video:url', 'og:video:secure_url']):
                    if meta.get('content'):
                        video_candidates.append(meta['content'])
                
                # Thu thập từ script data
                for script in soup.find_all('script', type=['application/json', 'text/javascript']):
                    try:
                        # Xử lý script dạng JSON
                        script_content = script.string or script.text
                        try:
                            data = json.loads(script_content)
                        except json.JSONDecodeError:
                            # Nếu không phải JSON, dùng văn bản gốc
                            data = script_content

                        def find_video_urls(obj):
                            urls = []
                            if isinstance(obj, dict):
                                # Tìm kiếm các trường video cụ thể của Pinterest
                                video_fields = ['video_url', 'videoUrl', 'url', 'high_res_url']
                                for field in video_fields:
                                    if field in obj and isinstance(obj[field], str):
                                        if any(ext in obj[field].lower() for ext in ['.mp4', '.m3u8']):
                                            urls.append(obj[field])
                                
                                # Tìm trong các đối tượng video
                                if 'videos' in obj:
                                    if isinstance(obj['videos'], dict):
                                        for video_data in obj['videos'].values():
                                            if isinstance(video_data, dict) and 'url' in video_data:
                                                urls.append(video_data['url'])
                                    elif isinstance(obj['videos'], list):
                                        for video_data in obj['videos']:
                                            if isinstance(video_data, dict) and 'url' in video_data:
                                                urls.append(video_data['url'])
                                
                                # Đệ quy tìm trong các đối tượng con
                                for v in obj.values():
                                    if isinstance(v, (dict, list)):
                                        urls.extend(find_video_urls(v))
                            elif isinstance(obj, list):
                                for item in obj:
                                    urls.extend(find_video_urls(item))
                            elif isinstance(obj, str):
                                # Tìm URL video trong chuỗi văn bản
                                video_patterns = [
                                    r'https?://[^"\']+?\.mp4[^"\']*',
                                    r'https?://[^"\']+?/video/[^"\']+',
                                    r'https?://v\.pinimg\.com[^"\']+',
                                ]
                                for pattern in video_patterns:
                                    urls.extend(re.findall(pattern, obj))
                            return urls

                        found_urls = find_video_urls(data)
                        if found_urls:
                            log(f'🎥 Tìm thấy {len(found_urls)} URL video trong script')
                            video_candidates.extend(found_urls)

                    except Exception as e:
                        log(f'⚠️ Lỗi khi xử lý script: {e}')
                        continue

                # Tìm phiên bản chất lượng cao nhất
                best_video = {'url': None, 'size': 0}
                for video_url in set(video_candidates):  # Loại bỏ trùng lặp
                    base_url = video_url.split('/hls/')[0] if '/hls/' in video_url else video_url.rsplit('/', 1)[0]
                    quality_variants = [
                        ('/originals/', '.mp4'),
                        ('/h265_4k/', '.mp4'),
                        ('/hevc_4k/', '.mp4'),
                        ('/4k/', '.mp4'),
                        ('/2160p/', '.mp4'),
                        ('/h265_1440p/', '.mp4'),
                        ('/1440p/', '.mp4'),
                        ('/1080p/', '.mp4')
                    ]
                    
                    for path, ext in quality_variants:
                        try:
                            test_url = f"{base_url}{path}video{ext}"
                            async with session.head(test_url, headers=headers) as resp:
                                if resp.status == 200:
                                    size = int(resp.headers.get('content-length', 0))
                                    if size > best_video['size']:
                                        best_video = {'url': test_url, 'size': size}
                                        log(f'📈 Tìm thấy phiên bản tốt hơn: {test_url} ({size/1024/1024:.1f}MB)')
                        except:
                            continue
                
                if best_video['url']:
                    return 'video', best_video['url']

            # Chỉ tìm ảnh nếu không phải là video
            if not is_video:
                img_sources = []
                
                # Kiểm tra các meta tags khác nhau
                meta_tags = [
                    ("meta", {"property": "og:image"}),
                    ("meta", {"name": "twitter:image"}),
                    ("meta", {"name": "pinterest:image"}),
                    ("meta", {"property": "og:image:url"}),
                    ("link", {"rel": "image_src"})
                ]
                
                log("🔍 Tìm kiếm ảnh trong meta tags...")
                for tag, attrs in meta_tags:
                    elem = soup.find(tag, attrs)
                    if elem:
                        url = elem.get('content') or elem.get('href')
                        if url:
                            if 'pinimg.com' in url:
                                url = re.sub(r'/\d+x/', '/originals/', url)
                                log(f'🔄 Nâng cấp ảnh lên chất lượng cao nhất: {url}')
                            img_sources.append(url)
                            log(f'✅ Tìm thấy ảnh từ {tag}: {url}')

                log("🔍 Tìm kiếm ảnh trong thẻ img...")
                for img in soup.find_all("img"):
                    src = img.get('src', '')
                    if not src:
                        continue
                    
                    if 'pinimg.com' in src:
                        src = re.sub(r'/\d+x/', '/originals/', src)
                    
                    if any(x in src.lower() for x in ['original', 'fullsize', '1200x', '736x']):
                        img_sources.append(src)
                        log(f'✅ Tìm thấy ảnh chất lượng cao: {src}')
                    elif 'src' in img.attrs:
                        img_sources.append(src)
                        log(f'✅ Tìm thấy ảnh: {src}')

                # Chọn ảnh có độ phân giải cao nhất
                log(f"🔍 Đánh giá {len(img_sources)} ảnh tìm thấy...")
                best_image = None
                max_resolution = 0

                for img_url in img_sources:
                    try:
                        if 'originals' in img_url:
                            log(f'🎯 Tìm thấy ảnh gốc: {img_url}')
                            return 'image', img_url

                        if 'pinimg.com' in img_url:
                            original_url = re.sub(r'/\d+x/', '/originals/', img_url)
                            log(f'🔄 Thử truy cập ảnh gốc: {original_url}')
                            try:
                                async with session.head(original_url, headers=headers) as response:
                                    if response.status == 200:
                                        log(f'✅ Ảnh gốc khả dụng!')
                                        return 'image', original_url
                            except:
                                log('⚠️ Không thể truy cập ảnh gốc, dùng ảnh thay thế')

                        res_match = re.search(r'(\d+)x(\d+)', img_url)
                        if res_match:
                            resolution = int(res_match.group(1)) * int(res_match.group(2))
                            log(f'📏 Ảnh {img_url} có độ phân giải: {res_match.group(1)}x{res_match.group(2)}')
                            if resolution > max_resolution:
                                max_resolution = resolution
                                best_image = img_url
                                log(f'📈 Cập nhật ảnh chất lượng cao nhất: {img_url}')
                    except Exception as e:
                        log(f'⚠️ Lỗi khi xử lý ảnh {img_url}: {e}')
                        continue

                if best_image:
                    log(f'✅ Chọn ảnh tốt nhất: {best_image}')
                    return 'image', best_image
                
                if img_sources:
                    log(f'⚠️ Không tìm được ảnh chất lượng cao, dùng ảnh đầu tiên: {img_sources[0]}')
                    return 'image', img_sources[0]

    except Exception as e:
        log(f'Lỗi khi trích xuất media: {e}')
    
    return None, None

# ====== COMMAND HANDLERS ======
@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    chat = await event.get_chat()
    log(f'Bot started in chat: {chat.id} ({"Group" if hasattr(chat, "title") else "Private"})')
    await event.reply(
        "👋 Xin chào! Tôi là bot tải ảnh/video từ Pinterest.\n"
        "Chỉ cần gửi link Pinterest, tôi sẽ tự động tải và gửi lại media cho bạn!\n"
        "🔗 Hỗ trợ cả link pinterest.com và pin.it"
    )

# ====== HANDLE ANY MESSAGE WITH PINTEREST LINK ======
@client.on(events.NewMessage)
async def handler(event):
    try:
        # Ignore commands
        if event.raw_text.startswith('/'):
            return

        text = event.raw_text
        if 'pinterest.com' not in text and 'pin.it' not in text:
            return

        chat = await event.get_chat()
        chat_info = f'Chat ID: {chat.id} ({"Group" if hasattr(chat, "title") else "Private"})'
        
        # Tìm tất cả các link Pinterest trong tin nhắn
        links = re.findall(r'(https?://(?:www\.)?(?:pinterest\.com/(?:[^\s]+|i/[^\s/]+)|pin\.it/[^\s]+))', text)
        if not links:
            return

        log(f'Phát hiện {len(links)} link Pinterest trong {chat_info}')
        await event.reply("🔍 Đang xử lý link Pinterest của bạn...")

        processed = []
        for link in links:
            try:
                log(f'Xử lý link: {link} trong {chat_info}')
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
                    log(f'✅ Đã tải thành công: {url}')
                else:
                    log(f'❌ Không thể tải: {url}')
            except Exception as e:
                log(f'❌ Lỗi khi xử lý {link}: {e}')

        if processed:
            try:
                # Gửi từng file một để tối ưu tốc độ
                for filename in processed:
                    try:
                        file_size = os.path.getsize(filename)
                        log(f'📤 Đang gửi file {filename} ({file_size/1024/1024:.1f}MB)...')
                        
                        # Gửi file
                        await event.reply(file=filename)
                        log(f'✅ Đã gửi thành công: {filename}')
                        
                        # Xóa file ngay sau khi gửi
                        os.remove(filename)
                        log(f'🧹 Đã xoá file: {filename}')
                    except Exception as e:
                        log(f'⚠️ Lỗi khi xử lý file {filename}: {e}')
                        # Đảm bảo xóa file ngay cả khi gặp lỗi
                        if os.path.exists(filename):
                            os.remove(filename)
                
                log(f'✨ Đã xử lý xong {len(processed)} file trong {chat_info}')
            except Exception as e:
                log(f'❌ Lỗi khi gửi files: {e}')
                # Dọn dẹp tất cả file còn sót lại
                for filename in processed:
                    if os.path.exists(filename):
                        try:
                            os.remove(filename)
                            log(f'🧹 Đã xoá file thừa: {filename}')
                        except:
                            pass
        else:
            await event.reply("❌ Không tìm thấy ảnh hoặc video hợp lệ.")
            log(f'⚠️ Không tìm thấy media hợp lệ trong {chat_info}')

    except Exception as e:
        await event.reply(f"❌ Đã xảy ra lỗi: {e}")
        log(f'❌ Lỗi: {e}')

# ====== START BOT ======
async def shutdown(signal_=None):
    """Cleanup function to gracefully shut down the bot"""
    if signal_:
        log(f"\n📢 Nhận tín hiệu: {signal_.name}")
    log("🔄 Đang dừng bot...")
    
    # Close the aiohttp session
    if session:
        log("🔒 Đóng phiên HTTP...")
        await session.close()
    
    # Disconnect the Telegram client
    if client and client.is_connected():
        log("🔌 Ngắt kết nối Telegram...")
        await client.disconnect()
    
    log("✅ Đã dọn dẹp xong!")
    log("👋 Tạm biệt!")

async def main():
    try:
        # Set up signal handlers for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop = asyncio.get_event_loop()
                loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))
            except NotImplementedError:
                # Windows doesn't support signal handlers
                pass
        
        log("🤖 Bot đang khởi động...")
        
        # Kiểm tra cấu hình
        if not api_id or not api_hash:
            log("❌ Thiếu thông tin cấu hình API")
            log("ℹ️ Hãy chạy lại bot và nhập API ID và API Hash")
            return
            
        log("🔄 Kết nối đến Telegram...")
        await client.start()
        
        me = await client.get_me()
        log(f"✅ Bot đã sẵn sàng! (@{me.username})")
        log("📝 Sử dụng /start trong chat để bắt đầu")
        log("⌛ Đang chờ tin nhắn...")
        log("💡 Nhấn Ctrl+C để dừng bot...")
        
        await client.run_until_disconnected()
    except ValueError as ve:
        log(f"❌ Lỗi cấu hình: {ve}")
        log("ℹ️ Hãy xoá file bot_config.json và chạy lại bot")
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        log(f"❌ Lỗi khởi động bot: {e}")
        log(f"📋 Chi tiết lỗi:\n{error_details}")
    finally:
        await shutdown()

# Run the bot
if __name__ == '__main__':
    try:
        # Import signal here to avoid issues on non-Unix platforms
        import signal
        
        # Kiểm tra file cấu hình
        if not os.path.exists(CONFIG_FILE):
            log("⚙️ Chưa có file cấu hình, bắt đầu thiết lập...")
        
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # Handled by signal handlers
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        log(f"❌ Lỗi không mong muốn: {e}")
        log(f"📋 Chi tiết lỗi:\n{error_details}")
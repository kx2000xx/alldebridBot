import os
from dotenv import load_dotenv
from telethon import TelegramClient, events
from termcolor import colored
from tqdm import tqdm
from urllib.parse import unquote
import re
import aiofiles
import asyncio
import aiohttp
import time
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()
# Load the ApiKey
API_KEY = os.getenv("API_KEY")
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ENABLED_USERS = os.getenv("ENABLED_USERS")
BLOCKED_USERS = os.getenv("BLOCKED_USERS")
AUTHORIZED_GROUP_ID = os.getenv("AUTHORIZED_GROUP_ID")
bot = TelegramClient('bot', TELEGRAM_API_ID, TELEGRAM_API_HASH).start(bot_token=TELEGRAM_BOT_TOKEN)
timeout = aiohttp.ClientTimeout(total=86400)  # 24 hours timeout for large file
users_requests = {}
ad = "\n\n\nDeveloped By Zedni Inc.\nWebsite: zedni.ca\nInstagram: @zedninc\nWhatsapp: +14374344702"


def clear_dictionary():
    users_requests.clear()
    print(f"Dictionary cleared at {time.strftime('%Y-%m-%d %H:%M:%S')}")

# Setup scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(clear_dictionary, 'interval', hours=24)
scheduler.start()



async def getFileNameFromLink(name):
    if name.find('/'):
        name = unquote(name.rsplit('/', 1)[1])
    name = re.sub(r'[\\/*?:"<>|]',"",name)
    return name


async def upload_to_gofile_with_progress(file_path):
    """
    Alternative async upload with better progress tracking
    """
    try:
        # Get server
        print(colored("Finding best server...", "light_blue"))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get('https://api.gofile.io/servers') as response:
                server_data = await response.json()
                server = server_data['data']['servers'][0]['name']
                print(colored(f"Using server: {server}", "light_blue"))

        # Validate file
        if not os.path.exists(file_path):
            print(colored(f"ERROR: File '{file_path}' not found!", "light_red"))
            return None

        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)

        # Initialize progress bar
        progress_bar = tqdm(
            total=file_size,
            unit='B',
            unit_scale=True,
            desc=f"Uploading {file_name}",
            colour="green"
        )

        # Custom payload generator with progress tracking
        async def file_sender():
            async with aiofiles.open(file_path, 'rb') as f:
                chunk = await f.read(153600)  # 8KB chunks
                while chunk:
                    progress_bar.update(len(chunk))
                    yield chunk
                    chunk = await f.read(153600)
            progress_bar.close()

        # Upload file
        url = f'https://{server}.gofile.io/uploadFile'
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Create form data
            data = aiohttp.FormData()
            data.add_field('file', 
                          file_sender(),
                          filename=file_name,
                          content_type='application/octet-stream')

            async with session.post(url, data=data) as response:
                if response.status == 200:
                    upload_data = await response.json()
                    
                    if upload_data.get('status') == 'ok':
                        download_link = upload_data['data']['downloadPage']
                        print(colored("✓ Upload completed successfully!", "light_green"))
                        os.remove(file_path)
                        return download_link
                    else:
                        error_msg = upload_data.get('message', 'Unknown error')
                        print(colored(f"✗ Upload failed: {error_msg}", "light_red"))
                        return None
                else:
                    print(colored(f"✗ HTTP Error: {response.status}", "light_red"))
                    return None

    except asyncio.TimeoutError:
        print(colored("✗ Upload timeout", "light_red"))
        return None
    except aiohttp.ClientError as e:
        print(colored(f"✗ Network error: {e}", "light_red"))
        return None
    except Exception as e:
        print(colored(f"✗ Unexpected error: {e}", "light_red"))
        return None



async def downloader(debrid_link):
    """
    Asynchronous file downloader with progress bar
    """
    if not os.path.isdir('files'):
        os.mkdir('files')
        
    print(colored("Start Downloading.....", "light_green"))
    
    filename = await getFileNameFromLink(debrid_link)
    destination = 'files/' + filename
    print(colored("FileName: " + filename, "light_yellow"))
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(debrid_link) as response:
            if response.status != 200:
                raise RuntimeError(colored(f"Download failed with status: {response.status}", "light_red"))
                
            total_size = int(response.headers.get("content-length", 0))
            
            # Initialize progress bar
            progress_bar = tqdm(
                total=total_size, 
                unit="B", 
                unit_scale=True, 
                colour="red",
                desc="Downloading"
            )
            
            async with aiofiles.open(destination, "wb") as file:
                async for data in response.content.iter_chunked(153600):  # 1KB chunks
                    await file.write(data)
                    progress_bar.update(len(data))
                    
            progress_bar.close()
            
            # Verify download size
            downloaded_size = os.path.getsize(destination)
            if total_size != 0 and downloaded_size != total_size:
                os.remove(destination)  # Clean up incomplete file
                raise RuntimeError(colored("Could not download file completely", "light_red"))
                
    print(colored("DONE!!", "light_green"))
    print(colored("Your file is saved in: ", "light_green") + 
          colored(os.path.join(os.getcwd(), "files\n\n"), "light_yellow"))
    
    return filename, destination


async def get_debrid_link(api_key, link):
    """
    Get the debrid link from AllDebrid asynchronously
    """
    url = f"https://api.alldebrid.com/v4/link/unlock?apikey={api_key}&agent=TelegramBot&link={link}"
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                if data['status'] == 'success':
                    return data['data']['link'], data['data']['filesize']
                else:
                    print(f"API Error: {data}")
                    return False
            else:
                print(f"HTTP Error: {response.status}")
                return False


@bot.on(events.NewMessage(pattern='/dl *'))
async def download_link(event):
    if event.is_private:
        await event.reply("❌ This bot only works in specific group. Please join the following group and use it there.\nhttps://t.me/+4m_yZcXqi901Mzc5")
        return
    # if str(event.sender.username) in ENABLED_USERS:
    
    username = event.sender.username
    if username in BLOCKED_USERS:
        await event.reply(message="You're Blocked!")
        return
    if users_requests.get(username, None):
        if users_requests[username] >=2:
            await event.reply(message="You've hit the usage limit.\nYou have to wait 24 hours from your last request.",)
            return
    if event.chat_id in AUTHORIZED_GROUP_ID:
        link = event.raw_text
        # if the link doesn't appear to be a link, then return
        if link.startswith("/dl"):
            link = link[4:].strip()
        if not (link.startswith("http") or link.startswith("https")):
            await event.reply("This is not a link.")
            return
        try:
            debrid_link, filesize = await get_debrid_link(API_KEY, link)
        except:
            await event.reply("Something went wrong, ُEither the link is dead or website it not supported. please try again later.")
            return
        if debrid_link:
            if filesize <= 8589934592:
                print("User: " + str(
                    event.sender.username) + " requested link: " + link + " and got: " + debrid_link + " as a result.")
                # await event.reply(f"Here is your debrid link: {debrid_link}")
                await event.reply("Your request is under preparation. I'll will send it here once its ready")
                filename, destination = await downloader(debrid_link)
                download_link = await upload_to_gofile_with_progress(destination)
                await event.reply(message=f"Requester: @{username}\n```{filename}```\n{download_link}{ad}",)
                if users_requests.get(username, None):
                    users_requests[username] += 1
                else:
                    users_requests[username] = 1
                print(users_requests)
            else:
                await event.reply(message="Filesize exceeded the 8GB limit.",)    
        else:
            await event.reply("Something went wrong, ُEither the link is dead or website it not supported. please try again later.")
    else:
        await event.reply("❌ This bot only works in specific group. Please join the following group and use it there.\nhttps://t.me/+4m_yZcXqi901Mzc5")

@bot.on(events.NewMessage(pattern='/help'))
@bot.on(events.NewMessage(pattern='/start'))
async def help(event):
    # if str(event.sender.username) in ENABLED_USERS:
    username = event.sender.username
    if username in BLOCKED_USERS:
        await event.reply(message="You're Blocked!")
        return
    if event.chat_id in AUTHORIZED_GROUP_ID:
        await event.reply(f"Supported Hosts:\n- RapidGator\n- Google Drive\n- Mega (Not folder)\n- TurboBit\n\nUsage:\n/dl http://rapidgator.net/...{ad}")
    else:
        await event.reply("❌ This bot only works in specific group. Please join the following group and use it there.\nhttps://t.me/+4m_yZcXqi901Mzc5")
    # else:
    #     await event.reply("You are not allowed to use this bot.")


def main():
    """Start the bot."""
    print("Starting the bot...")
    print("Loggin with id: " + str(TELEGRAM_API_ID))
    # print("Enabled users: " + str(ENABLED_USERS))
    bot.run_until_disconnected()


if __name__ == '__main__':
    main()
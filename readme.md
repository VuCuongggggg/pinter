# Pinterest Video Downloader

This is a simple Python script developed by Harshit to download videos from Pinterest.

The script makes use of popular Python libraries including requests, BeautifulSoup, tqdm, re, and datetime. It downloads video content from Pinterest by parsing the HTML content and identifying the source of the video. 

## Dependencies

To run this script, you'll need the following Python libraries:
- requests
- BeautifulSoup
- tqdm
- re
- datetime

You can install these libraries using pip:
```shell
pip install requests beautifulsoup4 tqdm
```
**Note**: re and datetime are both standard libraries in Python, so you don't need to install them.

## How to use

To use this script:
1. Make sure you have all dependencies installed.
2. Configure the bot:
   - When running for the first time, you'll be prompted to enter:
     - Telegram API ID
     - Telegram API Hash
     - Target Group ID (where media will be sent)
   - These settings will be saved in `bot_config.json`
   - You can reconfigure anytime by deleting `bot_config.json`
3. Run the script using python command in terminal:
    ```shell
    python main.py
    ```
4. The bot will start and process any Pinterest links sent to it.

The script will validate the URL and extract the video source. It will then download the video as an MP4 file, with the current date and time as part of the filename.

## Limitations

This script is designed to work with Pinterest's specific HTML structure as of the time of its creation. If Pinterest changes their website structure, the script may not work as expected.

Additionally, the script currently only supports direct Pinterest URLs or "pin.it" short URLs. Other URL structures may not work.

## License

This script is provided as-is under the MIT license. Feel free to modify and distribute, but please maintain original attribution to the creator.
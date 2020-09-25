# Church-Bot
This is a bot for ChurchTools written in Python. It uses redis for caching and directly accesses the [ChurchTools-API](https://feg-karlsruhe.church.tools/api).

# Features
- :bust_in_silhouette: Information about **people**, search using name/phone number
- :church: Information about current **room reservations**
- :calendar: Information about current **calendar entries**
- :musical_note: Search and download **songs**
- :busts_in_silhouette: Information about **groups**
- :birthday: Show current **birthdays**

# Getting Started
1. Install and start [redis](https://redis.io/)
2. Install the requirements (preferably in a [virtualenv](https://virtualenv.pypa.io)): `pip3 install -r requirements.txt`
3. Create a [Telegram Bot](https://core.telegram.org/bots) using the [BotFather](https://t.me/botfather)
4. Get your token, which looks like `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`
5. Set the environment variable (e.g. using `export`) `BOT_TOKEN=..`
6. Start the bot: `python3 churchbot.py`
7. Talk to your bot on Telegram

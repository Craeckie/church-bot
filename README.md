# Church-Bot
This is a bot for ChurchTools written in Python. It uses redis for caching and directly accesses the [ChurchTools-API](https://feg-karlsruhe.church.tools/api).

[Try it out on Telegram!](https://t.me/fegka_bot)

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

# Developer Information
This bot uses [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot).

The ChurchTools-API is currently undergoing major changes. Some functions are still only available via the old `?q=church{module}/ajax` format, e.g. `?q=churchdb/ajax`. These rather poorly documented and often require tracking the Ajax calls and guessing the meaning of the parameters. Other functions use the new `api/` and are documented in the official [reference](https://feg-karlsruhe.church.tools/api).

The code is not particularly readable or documented. Especially the entry function is quite a mess. This could be restructured to a more Object Oriented style using base and derived classes. An example for this is the implementation of bookings and calendar. Because they share several functions these are provided in a base class.

Feel free to open issues and pull requests are welcome!

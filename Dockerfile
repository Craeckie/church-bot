FROM python:3-slim

RUN apt update && apt upgrade -y && apt install -y --no-install-recommends locales libzbar0 python3-matplotlib && \
    echo 'de_DE.UTF-8 UTF-8' >> /etc/locale.gen && \
    locale-gen && update-locale LANG=de_DE.UTF-8 LC_ALL=de_DE.UTF-8 && \
    pip install matplotlib python-telegram-bot pytz requests beautifulsoup4 icalendar phonenumbers Flask redis vobject pyzbar pillow \
    && apt-get clean && rm -rf /var/lib/apt/* /var/cache/apt/*

# COPY run.sh /root/
WORKDIR /root/bots

CMD ["bash", "/root/run.sh"]

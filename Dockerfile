FROM python:3-slim

RUN apt update && apt upgrade -y && apt install -y --no-install-recommends locales libzbar0 && \
    echo 'de_DE.UTF-8 UTF-8' >> /etc/locale.gen && \
    locale-gen && update-locale LANG=de_DE.UTF-8 LC_ALL=de_DE.UTF-8 && \
    pip install --upgrade pip \
    && apt-get clean && rm -rf /var/lib/apt/* /var/cache/apt/*

# COPY run.sh /root/
ADD ./ /churchbot
WORKDIR /churchbot

RUN python3 -m venv ./env && \
    . /opt/venv/bin/activate && \
    pip install -r requirements.txt && \
    chown -R ww-data:www-data ./

USER www-data

CMD ". /opt/venv/bin/activate && exec python -m churchbot"

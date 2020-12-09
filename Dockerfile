FROM python:3-slim

RUN apt update && apt upgrade -y && apt install -y --no-install-recommends locales libzbar0 && \
    echo 'de_DE.UTF-8 UTF-8' >> /etc/locale.gen && \
    locale-gen && update-locale LANG=de_DE.UTF-8 LC_ALL=de_DE.UTF-8 && \
    pip install --upgrade pip && \
    mkdir -p /churchbot && \
    apt-get clean && rm -rf /var/lib/apt/* /var/cache/apt/*

ADD ./requirements.txt /churchbot/
WORKDIR /churchbot

RUN python3 -m venv ./env && \
    . ./env/bin/activate && \
    pip install -r requirements.txt

ADD ./ /churchbot
RUN chown -R www-data:www-data ./

USER www-data

CMD ["sh", "-c", ". ./env/bin/activate && exec python -m churchbot"]

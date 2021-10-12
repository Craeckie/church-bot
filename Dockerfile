FROM python:3-slim

RUN apt update && apt upgrade -y && apt install -y --no-install-recommends locales libzbar0 zlib1g-dev libjpeg-dev && \
    echo 'de_DE.UTF-8 UTF-8' >> /etc/locale.gen && \
    locale-gen && update-locale LANG=de_DE.UTF-8 LC_ALL=de_DE.UTF-8 && \
    pip install --upgrade pip && \
    mkdir -p /bot && \
    apt-get clean && rm -rf /var/lib/apt/* /var/cache/apt/*

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /bot
ADD ./requirements.txt ./

RUN apt update && apt install -y --no-install-recommends build-essential && \
    pip install -r requirements.txt && \
    apt remove -y build-essential && apt autoremove -y && \
    apt-get clean && rm -rf /var/lib/apt/* /var/cache/apt/*

ADD ./ ./
RUN chown -R www-data:www-data ./

USER www-data

CMD ["python", "-m", "churchbot"]

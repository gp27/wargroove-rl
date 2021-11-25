FROM ubuntu:bionic-20210930 as base

RUN apt update
RUN apt -y install ssh htop
RUN apt -y install python3-pip python3-dev cmake libopenmpi-dev
RUN apt -y install libpq-dev zlib1g-dev libgl1-mesa-dev libsdl2-dev libffi-dev

RUN pip3 install --upgrade pip
RUN pip3 install --upgrade setuptools

RUN useradd -ms /bin/bash selfplay
USER selfplay
ENV PATH="/home/selfplay/.local/bin:${PATH}"
WORKDIR /app

COPY --chown=selfplay:selfplay ./app/requirements.txt /app
RUN pip3 install -r /app/requirements.txt

COPY --chown=selfplay:selfplay ./app .

ENV PYTHONIOENCODING=utf-8
ENV LC_ALL=C.UTF-8
ENV export LANG=C.UTF-8

CMD bash

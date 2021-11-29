FROM stablebaselines/stable-baselines3 as base

RUN apt update && apt install -y --no-install-recommends \
  libsdl2-dev
#RUN apt -y install libpq-dev zlib1g-dev libgl1-mesa-dev libffi-dev

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

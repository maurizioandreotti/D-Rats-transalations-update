#!/bin/bash

# This is for use in a dockerfile or a github action to make sure
# that the required packages are installed.

set -uex

# Need to disable are-you-sure prompts during the installs
DEBIAN_FRONTEND=noninteractive
export DEBIAN_FRONTEND
# echo "APT::Get::Assume-Yes \"true\";" > /etc/apt/apt.conf.d/no-prompt
# echo "APT::Install-Recommends \"false\";" > \
#    /etc/apt/apt.conf.d/no-recommends

# Update to current and add packages
sudo -S -E apt-get --assume-yes update
sudo -S -E apt-get --assume-yes install aptitude
sudo -S -E aptitude --assume-yes safe-upgrade
sudo -S -E apt-get --assume-yes install \
    file \
    git \
    grep \
    pylint \
    python3 \
    python3-feedparser \
    python3-flask \
    python3-geopy \
    python3-gevent \
    python3-gi \
    python3-gi-cairo \
    python3-lxml \
    python3-pil \
    python3-serial

#!/bin/bash
# Warm up slk auth cache — keeps token+cookie fresh for Slack CLI
# Slack desktop app must be running when this script runs.

PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin
export PATH
/opt/homebrew/bin/slk auth > /dev/null 2>&1

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'ipetrash'


import math
import time
import os
from typing import Dict, Tuple
from pathlib import Path
import shutil

# pip install python-telegram-bot
from telegram import Update, ChatAction, ReplyKeyboardMarkup
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext, CommandHandler, PicklePersistence
from telegram.ext.dispatcher import run_async

import requests

import numpy as np
import PIL.Image

import config
from common import get_logger, log_func, catch_error
from deep_dream.main import render_deepdream_from_layer_by_unit


COMMAND_GET_ORIGINAL_PHOTO = 'Get original photo'
COMMAND_RESET = '<Reset>'
COMMAND_RETRY = '<Retry>'

COMMANDS_DEEP_DREAM = dict()
KEYBOARD_BUTTONS = []


def _add_row(commands: Dict[str, Tuple[str, int]]):
    COMMANDS_DEEP_DREAM.update(commands)
    KEYBOARD_BUTTONS.append(list(commands.keys()))


# COMMANDS_BUILDING
_add_row({
    '🏠 1': ('mixed4d_3x3_bottleneck_pre_relu', 65),
    '🏠 2': ('mixed4d_3x3_bottleneck_pre_relu', 66),
    '🏠 3': ('mixed4b_3x3_pre_relu', 95),
    '🏠 4': ('mixed4e_pool_reduce_pre_relu', 26),
    '🏠 5': ('mixed4c_pool_reduce_pre_relu', 29),
})

# COMMANDS_FLOWERS
_add_row({
    '🌻 1': ('mixed4d_3x3_bottleneck_pre_relu', 139),
    '🌻 2': ('mixed4c_3x3_pre_relu', 83),
    '🌻 3': ('mixed4c_3x3_pre_relu', 230),
    '🌻 4': ('mixed4d_3x3_pre_relu', 88),
    '🌻 5': ('mixed4c_pool_reduce_pre_relu', 41),
})

# COMMANDS_ANIMALS
_add_row({
    '🐻 1': ('mixed5a_5x5_pre_relu', 11),
    '🐻 2': ('mixed4e_pool_reduce_pre_relu', 27),
    '🐻 3': ('mixed5a_1x1_pre_relu', 0),
    '🐻 4': ('mixed5a_1x1_pre_relu', 1),
    '🐻 5': ('mixed5a_1x1_pre_relu', 81),
})

# COMMANDS_DOGS
_add_row({
    '🐕 1': ('mixed4b_5x5_pre_relu', 55),
    '🐕 2': ('mixed4e_pool_reduce_pre_relu', 29),
    '🐕 3': ('mixed5a_3x3_bottleneck_pre_relu', 100),
    '🐕 4': ('mixed5a_1x1_pre_relu', 47),
    '🐕 5': ('mixed5a_1x1_pre_relu', 175),
})

# COMMANDS_ANIMALS_2
_add_row({
    '🐈 1': ('mixed4d_5x5_pre_relu', 1),
    '🐈 2': ('mixed4e_pool_reduce_pre_relu', 105),
    '🦋 1': ('mixed5a_1x1_pre_relu', 63),
    '🐟 1': ('mixed5a_1x1_pre_relu', 158),
    '🐒 1': ('mixed5a_pool_reduce_pre_relu', 53),
})

# COMMANDS_BIRDS
_add_row({
    '🐦 1': ('mixed5b_3x3_bottleneck_pre_relu', 91),
    '🐦 2': ('mixed5b_3x3_bottleneck_pre_relu', 166),
    '🐦 3': ('mixed5b_3x3_bottleneck_pre_relu', 167),
    '🐦 4': ('mixed4e_pool_reduce_pre_relu', 50),
    '🐦 5': ('mixed4e_pool_reduce_pre_relu', 57),
})

# COMMANDS_OTHER
_add_row({
    '🌟 1': ('mixed3b_3x3_bottleneck_pre_relu', 109),
    '⚽ 1': ('mixed5a_1x1_pre_relu', 9),
    '🎡 1': ('mixed4c_pool_reduce_pre_relu', 1),
    '🚗 1': ('mixed4c_5x5_pre_relu', 14),
    '🚗 2': ('mixed4c_5x5_pre_relu', 63),
})

# COMMANDS_OTHER_2
_add_row({
    '🌪️ 1': ('mixed4d_3x3_bottleneck_pre_relu', 84),
    '🎆 1': ('mixed4d_3x3_bottleneck_pre_relu', 50),
    'Stones': ('mixed4d_3x3_bottleneck_pre_relu', 38),
    '⛰️ 1': ('mixed4d_3x3_bottleneck_pre_relu', 142),
    '✂️👂': ('mixed4d_3x3_bottleneck_pre_relu', 1),
})

# COMMANDS_FEARS
_add_row({
    '😱 1': ('mixed5a_3x3_pre_relu', 174),
    '😱 2': ('mixed5a_3x3_pre_relu', 190),
    '😱 3': ('mixed4d_3x3_bottleneck_pre_relu', 88),
    '😱 4': ('mixed4e_pool_reduce_pre_relu', 101),
    '😱 5': ('mixed5a_1x1_pre_relu', 3),
})

COMMANDS_DEEP_DREAM[COMMAND_GET_ORIGINAL_PHOTO] = None
COMMANDS_DEEP_DREAM[COMMAND_RETRY] = None


def get_reply_keyboard_markup() -> ReplyKeyboardMarkup:
    data = [
        [COMMAND_RESET, COMMAND_RETRY]
    ]
    data += KEYBOARD_BUTTONS
    data.append([COMMAND_GET_ORIGINAL_PHOTO])

    return ReplyKeyboardMarkup(data, resize_keyboard=True)


def get_file_name_image(user_id: int, need_last=False) -> Path:
    return config.DIR_IMAGES / f'{user_id}{"_last" if need_last else ""}.jpg'


def reset_img(user_id: int):
    file_name_orig = get_file_name_image(user_id)
    file_name_last = get_file_name_image(user_id, need_last=True)

    shutil.copy(file_name_orig, file_name_last)


def start_progress(context: CallbackContext):
    context.user_data['progress'] = True


def is_progress(context: CallbackContext) -> bool:
    return context.user_data.get('progress', False)


def finish_progress(context: CallbackContext):
    context.user_data['progress'] = False


log = get_logger(__file__)


@run_async
@catch_error(log)
@log_func(log)
def on_start(update: Update, context: CallbackContext):
    message = update.message
    message.reply_text('Send me a picture')


@run_async
@catch_error(log)
@log_func(log)
def on_photo(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    msg = 'Downloading a picture ...'
    log.debug(msg)
    progress_message = update.message.reply_text(msg + '\n⬜⬜⬜⬜⬜')

    context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    url = update.message.photo[-1].get_file().file_path

    rs = requests.get(url)

    progress_message.edit_text(msg + '\n⬛⬛⬛⬜⬜')

    file_name = get_file_name_image(user_id)
    with open(file_name, 'wb') as f:
        f.write(rs.content)

    reset_img(user_id)

    msg = 'Picture downloaded!'
    log.debug(msg)
    progress_message.edit_text(msg + '\n⬛⬛⬛⬛⬛')
    progress_message.delete()

    # Reset
    context.user_data['elapsed_secs'] = -1
    finish_progress(context)

    update.message.reply_text(
        'Deep dream are now available',
        reply_markup=get_reply_keyboard_markup()
    )


@run_async
@catch_error(log)
@log_func(log)
def on_deep_dream(update: Update, context: CallbackContext):
    message = update.message or update.edited_message
    command = message.text

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if is_progress(context):
        message.reply_text('Please wait, the command is currently running')
        return

    start_progress(context)
    try:
        file_name_orig = get_file_name_image(user_id)

        if command == COMMAND_GET_ORIGINAL_PHOTO:
            file_name = file_name_orig
        else:
            if command == COMMAND_RETRY:
                if 'last_command' not in context.user_data:
                    message.reply_text('First you need to execute the commands')
                    return

                command = context.user_data['last_command']

            elapsed_secs = context.user_data.get('elapsed_secs', -1)
            if elapsed_secs > 0:
                elapsed_secs = context.user_data['elapsed_secs']
                text = f'Wait ~{math.ceil(elapsed_secs)} seconds'
            else:
                text = 'Waiting ...'

            mess_wait = message.reply_text(text)

            file_name_last = get_file_name_image(user_id, True)
            file_name = file_name_last

            layer, unit = COMMANDS_DEEP_DREAM[command]

            t = time.perf_counter()

            img0 = PIL.Image.open(file_name_last)
            img0 = np.float32(img0)
            render_deepdream_from_layer_by_unit(img0, file_name_last, layer, unit)

            elapsed_secs = time.perf_counter() - t
            context.user_data['elapsed_secs'] = elapsed_secs

            log.debug(f'Command: {command!r}, elapsed_secs: {elapsed_secs:.2f} secs, saving to: {file_name_last}')

            mess_wait.delete()

            context.user_data['last_command'] = command

        context.bot.send_chat_action(chat_id, action=ChatAction.UPLOAD_PHOTO)

        message.reply_photo(
            open(file_name, 'rb')
        )

    finally:
        finish_progress(context)


@run_async
@catch_error(log)
@log_func(log)
def on_reset(update: Update, context: CallbackContext):
    message = update.message or update.edited_message
    user_id = update.effective_user.id

    reset_img(user_id)

    message.reply_text('Reset was successful')


@run_async
@catch_error(log)
@log_func(log)
def on_request(update: Update, context: CallbackContext):
    message = update.message or update.edited_message

    message.reply_text('Unknown command')


@catch_error(log)
def on_error(update: Update, context: CallbackContext):
    log.exception('Error: %s\nUpdate: %s', context.error, update)
    if update:
        message = update.message or update.edited_message
        message.reply_text(config.ERROR_TEXT)


def main():
    cpu_count = os.cpu_count()
    workers = cpu_count
    log.debug('System: CPU_COUNT=%s, WORKERS=%s', cpu_count, workers)

    log.debug('Start')

    persistence = PicklePersistence(filename='data.pickle')

    # Create the EventHandler and pass it your bot's token.
    updater = Updater(
        config.TOKEN,
        workers=workers,
        persistence=persistence,
        use_context=True
    )

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', on_start))
    dp.add_handler(MessageHandler(Filters.photo, on_photo))
    dp.add_handler(MessageHandler(Filters.text(COMMANDS_DEEP_DREAM), on_deep_dream))
    dp.add_handler(MessageHandler(Filters.text([COMMAND_RESET]), on_reset))
    dp.add_handler(MessageHandler(Filters.all, on_request))

    dp.add_error_handler(on_error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until the you presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    while True:
        try:
            main()
        except:
            log.exception('')

            timeout = 15
            log.info(f'Restarting the bot after {timeout} seconds')
            time.sleep(timeout)

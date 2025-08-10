import os
import logging
import re
import time
from datetime import timedelta
from typing import Optional

from telegram import Update, ChatPermissions
from telegram.constants import ChatType
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Конфигурация
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') or '8267666398:AAHoqr5l306G_EAWGreAlUtkODY-KOrSn60'


# Вспомогательные функции
def parse_duration(text: str) -> Optional[timedelta]:
    m = re.fullmatch(r"(\d+)([mhd])", (text or '').strip().lower())
    if not m:
        return None
    v, u = int(m.group(1)), m.group(2)
    return timedelta(minutes=v) if u == 'm' else timedelta(hours=v) if u == 'h' else timedelta(days=v)


async def get_admin_ids(update: Update, context: ContextTypes.DEFAULT_TYPE) -> set[int]:
    chat = update.effective_chat
    if not chat or chat.type == ChatType.PRIVATE:
        return set()
    admins = await context.bot.get_chat_administrators(chat.id)
    return {a.user.id for a in admins}


def need_reply(update: Update) -> bool:
    return bool(update.effective_message and update.effective_message.reply_to_message)


# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text('Бот‑модератор запущен. Дайте права администратора в группе/канале.')


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Команды:\n"
        "/info — инфо о пользователе (в ответ)\n"
        "/warn [причина] — предупреждение (в ответ)\n"
        "/kick [причина] — кик (в ответ)\n"
        "/mute <10m|2h|1d> [причина] — мут (в ответ)\n"
        "/unmute — снять мут (в ответ)\n"
        "/ban [причина] — бан (в ответ)\n"
        "/unban — разбан (в ответ)\n"
    )


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = msg.reply_to_message.from_user if msg.reply_to_message else msg.from_user
    await msg.reply_text(
        f"ID: {user.id}\nИмя: {user.first_name}\nЮзернейм: @{user.username or 'нет'}\nБот: {'Да' if user.is_bot else 'Нет'}"
    )


async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not need_reply(update):
        await msg.reply_text('Нужно ответить на сообщение пользователя.')
        return
    admins = await get_admin_ids(update, context)
    if msg.from_user.id not in admins:
        await msg.reply_text('Только администраторы могут это делать.')
        return
    reason = ' '.join(context.args) if context.args else 'без причины'
    await msg.reply_text(f"Предупреждение выдано ({reason}).")


async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg, chat = update.effective_message, update.effective_chat
    if not need_reply(update):
        await msg.reply_text('Нужно ответить на сообщение пользователя.')
        return
    admins = await get_admin_ids(update, context)
    if msg.from_user.id not in admins:
        await msg.reply_text('Только администраторы могут это делать.')
        return
    target = msg.reply_to_message.from_user
    if target.id in admins:
        await msg.reply_text('Нельзя кикнуть администратора.')
        return
    reason = ' '.join(context.args) if context.args else 'без причины'
    try:
        await context.bot.ban_chat_member(chat.id, target.id)
        await context.bot.unban_chat_member(chat.id, target.id)
        await msg.reply_text(f"Пользователь кикнут ({reason}).")
    except Exception as e:
        await msg.reply_text(f"Ошибка: {e}")


async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg, chat = update.effective_message, update.effective_chat
    if not need_reply(update):
        await msg.reply_text('Нужно ответить на сообщение пользователя.')
        return
    if not context.args:
        await msg.reply_text('Укажите время: /mute 10m')
        return
    admins = await get_admin_ids(update, context)
    if msg.from_user.id not in admins:
        await msg.reply_text('Только администраторы могут это делать.')
        return
    target = msg.reply_to_message.from_user
    if target.id in admins:
        await msg.reply_text('Нельзя мутить администратора.')
        return
    duration = parse_duration(context.args[0])
    if not duration:
        await msg.reply_text('Неверный формат. Примеры: 10m, 2h, 1d')
        return
    reason = ' '.join(context.args[1:]) if len(context.args) > 1 else 'без причины'
    until_date = int(time.time() + duration.total_seconds())
    try:
        await context.bot.restrict_chat_member(
            chat.id,
            target.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date,
        )
        await msg.reply_text(f"Пользователь замьючен на {context.args[0]} ({reason}).")
    except Exception as e:
        await msg.reply_text(f"Ошибка: {e}")


async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg, chat = update.effective_message, update.effective_chat
    if not need_reply(update):
        await msg.reply_text('Нужно ответить на сообщение пользователя.')
        return
    admins = await get_admin_ids(update, context)
    if msg.from_user.id not in admins:
        await msg.reply_text('Только администраторы могут это делать.')
        return
    target = msg.reply_to_message.from_user
    try:
        await context.bot.restrict_chat_member(
            chat.id,
            target.id,
            permissions=ChatPermissions(can_send_messages=True),
        )
        await msg.reply_text("Пользователь размьючен.")
    except Exception as e:
        await msg.reply_text(f"Ошибка: {e}")


async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg, chat = update.effective_message, update.effective_chat
    if not need_reply(update):
        await msg.reply_text('Нужно ответить на сообщение пользователя.')
        return
    admins = await get_admin_ids(update, context)
    if msg.from_user.id not in admins:
        await msg.reply_text('Только администраторы могут это делать.')
        return
    target = msg.reply_to_message.from_user
    if target.id in admins:
        await msg.reply_text('Нельзя банить администратора.')
        return
    reason = ' '.join(context.args) if context.args else 'без причины'
    try:
        await context.bot.ban_chat_member(chat.id, target.id)
        await msg.reply_text(f"Пользователь забанен ({reason}).")
    except Exception as e:
        await msg.reply_text(f"Ошибка: {e}")


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg, chat = update.effective_message, update.effective_chat
    if not need_reply(update):
        await msg.reply_text('Ответьте на сообщение пользователя (или пришлите его ID отдельной командой — не реализовано в упрощённой версии).')
        return
    admins = await get_admin_ids(update, context)
    if msg.from_user.id not in admins:
        await msg.reply_text('Только администраторы могут это делать.')
        return
    target = msg.reply_to_message.from_user
    try:
        await context.bot.unban_chat_member(chat.id, target.id, only_if_banned=True)
        await msg.reply_text("Пользователь разбанен.")
    except Exception as e:
        await msg.reply_text(f"Ошибка: {e}")


def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN == 'YOUR_TOKEN':
        raise RuntimeError('Укажите TELEGRAM_BOT_TOKEN или впишите токен в код.')

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_cmd))
    app.add_handler(CommandHandler('info', info))
    app.add_handler(CommandHandler('warn', warn))
    app.add_handler(CommandHandler('kick', kick))
    app.add_handler(CommandHandler('mute', mute))
    app.add_handler(CommandHandler('unmute', unmute))
    app.add_handler(CommandHandler('ban', ban))
    app.add_handler(CommandHandler('unban', unban))

    app.run_polling(close_loop=False)


if __name__ == '__main__':
    main()
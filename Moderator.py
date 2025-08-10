import os
import logging
import re
import time
from datetime import timedelta
from typing import Optional

from telegram import Update, ChatPermissions
from telegram.constants import ChatType
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.helpers import mention_html

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Токен: используем переменную окружения TELEGRAM_BOT_TOKEN или константу как запасной вариант
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') or 'YOUR_TOKEN'


# --- Вспомогательные функции ---

def parse_duration(time_str: str) -> Optional[timedelta]:
    """Парсит строку времени (10m, 2h, 1d) и возвращает timedelta."""
    match = re.match(r"^(\d+)([mhd])$", time_str.lower().strip())
    if not match:
        return None

    value, unit = int(match.group(1)), match.group(2)
    if unit == 'm':
        return timedelta(minutes=value)
    if unit == 'h':
        return timedelta(hours=value)
    if unit == 'd':
        return timedelta(days=value)
    return None


async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором чата."""
    chat = update.effective_chat
    if chat is None or chat.type == ChatType.PRIVATE:
        return False
    try:
        admins = await context.bot.get_chat_administrators(chat.id)
        return any(admin.user.id == user_id for admin in admins)
    except Exception as error:
        logger.error("Не удалось получить администраторов: %s", error)
        return False


async def target_is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int) -> bool:
    chat = update.effective_chat
    if chat is None or chat.type == ChatType.PRIVATE:
        return False
    try:
        admins = await context.bot.get_chat_administrators(chat.id)
        return any(admin.user.id == target_user_id for admin in admins)
    except Exception as error:
        logger.error("Не удалось проверить права цели: %s", error)
        return False


def ensure_reply(update: Update) -> bool:
    return bool(update.message and update.message.reply_to_message)


# --- Команды ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        'Привет! Я бот‑модератор. Добавьте меня в группу и дайте права администратора.'
    )


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = message.reply_to_message.from_user if message.reply_to_message else message.from_user

    user_mention = mention_html(user.id, user.first_name)
    text = (
        f"<b>Пользователь:</b> {user_mention}\n"
        f"<b>ID:</b> <code>{user.id}</code>\n"
        f"<b>Имя:</b> {user.first_name}\n"
        f"<b>Фамилия:</b> {user.last_name or 'Нет'}\n"
        f"<b>Юзернейм:</b> @{user.username or 'Нет'}\n"
        f"<b>Это бот?:</b> {'Да' if user.is_bot else 'Нет'}"
    )
    await message.reply_html(text)


async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message

    if not await is_user_admin(update, context, message.from_user.id):
        await message.reply_text('Вы не являетесь администратором.')
        return

    if not ensure_reply(update):
        await message.reply_text('Используйте эту команду в ответ на сообщение.')
        return

    target = message.reply_to_message.from_user
    reason = ' '.join(context.args) if context.args else 'Без указания причины'

    target_mention = mention_html(target.id, target.first_name)
    admin_mention = mention_html(message.from_user.id, message.from_user.first_name)

    await message.reply_html(
        f"{target_mention}, вы получили предупреждение от {admin_mention}!\n<b>Причина:</b> {reason}"
    )


async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat

    if not await is_user_admin(update, context, message.from_user.id):
        await message.reply_text('Вы не являетесь администратором.')
        return

    if not ensure_reply(update):
        await message.reply_text('Используйте эту команду в ответ на сообщение.')
        return

    target = message.reply_to_message.from_user

    if await target_is_admin(update, context, target.id):
        await message.reply_text('Нельзя применять это действие к администратору.')
        return

    reason = ' '.join(context.args) if context.args else 'Без указания причины'

    try:
        # "Кик" — бан с последующим разбаном, чтобы пользователь мог вернуться по ссылке
        await context.bot.ban_chat_member(chat_id=chat.id, user_id=target.id)
        await context.bot.unban_chat_member(chat_id=chat.id, user_id=target.id)

        await message.reply_html(
            f"Пользователь {mention_html(target.id, target.first_name)} был кикнут из чата.\n"
            f"<b>Причина:</b> {reason}"
        )
    except Exception as error:
        logger.error("Ошибка при кике: %s", error)
        await message.reply_text(f"Не удалось кикнуть пользователя. Ошибка: {error}")


async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat

    if not await is_user_admin(update, context, message.from_user.id):
        await message.reply_text('Вы не являетесь администратором.')
        return

    if not ensure_reply(update):
        await message.reply_text('Используйте эту команду в ответ на сообщение.')
        return

    if not context.args:
        await message.reply_text('Укажите время мута! Например: /mute 10m флуд')
        return

    duration = parse_duration(context.args[0])
    if not duration:
        await message.reply_text('Неверный формат времени. Используйте: 10m (минуты), 2h (часы), 1d (дни).')
        return

    target = message.reply_to_message.from_user

    if await target_is_admin(update, context, target.id):
        await message.reply_text('Нельзя мутить администратора.')
        return

    reason = ' '.join(context.args[1:]) if len(context.args) > 1 else 'Без указания причины'
    until_date = int(time.time() + duration.total_seconds())

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=target.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date,
        )
        await message.reply_html(
            f"Пользователь {mention_html(target.id, target.first_name)} был заглушен на {context.args[0]}.\n"
            f"<b>Причина:</b> {reason}"
        )
    except Exception as error:
        logger.error("Ошибка при муте: %s", error)
        await message.reply_text(f"Не удалось заглушить пользователя. Ошибка: {error}")


async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat

    if not await is_user_admin(update, context, message.from_user.id):
        await message.reply_text('Вы не являетесь администратором.')
        return

    if not ensure_reply(update):
        await message.reply_text('Используйте эту команду в ответ на сообщение.')
        return

    target = message.reply_to_message.from_user

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=target.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        await message.reply_html(
            f"Пользователь {mention_html(target.id, target.first_name)} был размучен."
        )
    except Exception as error:
        logger.error("Ошибка при размуте: %s", error)
        await message.reply_text(f"Не удалось размутить пользователя. Ошибка: {error}")


async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat

    if not await is_user_admin(update, context, message.from_user.id):
        await message.reply_text('Вы не являетесь администратором.')
        return

    if not ensure_reply(update):
        await message.reply_text('Используйте эту команду в ответ на сообщение.')
        return

    target = message.reply_to_message.from_user

    if await target_is_admin(update, context, target.id):
        await message.reply_text('Нельзя банить администратора.')
        return

    reason = ' '.join(context.args) if context.args else 'Без указания причины'

    try:
        await context.bot.ban_chat_member(chat_id=chat.id, user_id=target.id)
        await message.reply_html(
            f"Пользователь {mention_html(target.id, target.first_name)} был забанен.\n<b>Причина:</b> {reason}"
        )
    except Exception as error:
        logger.error("Ошибка при бане: %s", error)
        await message.reply_text(f"Не удалось забанить пользователя. Ошибка: {error}")


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat

    if not await is_user_admin(update, context, message.from_user.id):
        await message.reply_text('Вы не являетесь администратором.')
        return

    if not ensure_reply(update):
        await message.reply_text('Используйте эту команду в ответ на сообщение забаненного пользователя или укажите его ID.')
        return

    target = message.reply_to_message.from_user

    try:
        await context.bot.unban_chat_member(chat_id=chat.id, user_id=target.id, only_if_banned=True)
        await message.reply_html(
            f"Пользователь {mention_html(target.id, target.first_name)} был разбанен."
        )
    except Exception as error:
        logger.error("Ошибка при разбане: %s", error)
        await message.reply_text(f"Не удалось разбанить пользователя. Ошибка: {error}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Доступные команды:\n"
        "/start — приветствие\n"
        "/info — информация о пользователе (в ответ или о себе)\n"
        "/warn [причина] — предупреждение (в ответ)\n"
        "/kick [причина] — кик (в ответ)\n"
        "/mute <10m|2h|1d> [причина] — мут на время (в ответ)\n"
        "/unmute — снять мут (в ответ)\n"
        "/ban [причина] — бан (в ответ)\n"
        "/unban — разбан (в ответ)\n"
    )
    await update.effective_message.reply_text(text)


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text('Неизвестная команда. Используйте /help.')


async def on_startup(app):
    logger.info("Бот запущен и работает…")


def build_application():
    if not BOT_TOKEN or BOT_TOKEN == 'YOUR_TOKEN':
        raise RuntimeError(
            'Пожалуйста, укажите токен бота в переменной окружения TELEGRAM_BOT_TOKEN или в константе BOT_TOKEN.'
        )
    return ApplicationBuilder().token(BOT_TOKEN).build()


def main() -> None:
    application = build_application()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CommandHandler("warn", warn))
    application.add_handler(CommandHandler("kick", kick))
    application.add_handler(CommandHandler("mute", mute))
    application.add_handler(CommandHandler("unmute", unmute))
    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("unban", unban))

    # Неизвестные команды можно отлавливать через MessageHandler с Filters.COMMAND,
    # но чтобы не добавлять дополнительные импорты, оставим минимальный набор.

    application.run_polling(close_loop=False, post_init=on_startup)


if __name__ == '__main__':
    main()
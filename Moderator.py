import logging
import re
import time
from datetime import timedelta
from telegram import Update, ParseMode, ChatPermissions
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram.utils.helpers import mention_html

# ВАЖНО: Вставьте сюда свой токен, полученный от @BotFather
BOT_TOKEN = 'YOUR_TOKEN' 

# Включаем логирование для отладки
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Вспомогательная функция для разбора времени ---

def parse_duration(time_str: str) -> timedelta or None:
    """Парсит строку времени (10m, 2h, 1d) и возвращает объект timedelta."""
    match = re.match(r"(\d+)([mhd])", time_str.lower())
    if not match:
        return None
    
    value, unit = int(match.group(1)), match.group(2)
    
    if unit == 'm':
        return timedelta(minutes=value)
    elif unit == 'h':
        return timedelta(hours=value)
    elif unit == 'd':
        return timedelta(days=value)
    return None

# --- Обработчики команд ---

def start(update: Update, context: CallbackContext) -> None:
    """Отправляет приветственное сообщение при команде /start."""
    update.message.reply_text('Привет! Я бот-администратор. Добавьте меня в группу и дайте права администратора, чтобы я мог работать.')

def is_user_admin(update: Update, context: CallbackContext, user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором чата."""
    if update.effective_chat.type == 'private':
        return False
    admins = context.bot.get_chat_administrators(update.effective_chat.id)
    return any(admin.user.id == user_id for admin in admins)

def info(update: Update, context: CallbackContext) -> None:
    """Показывает информацию о пользователе."""
    user_to_check = update.message.reply_to_message.from_user if update.message.reply_to_message else update.message.from_user
    
    user_mention = mention_html(user_to_check.id, user_to_check.first_name)
    
    info_text = (
        f"<b>Пользователь:</b> {user_mention}\n"
        f"<b>ID:</b> <code>{user_to_check.id}</code>\n"
        f"<b>Имя:</b> {user_to_check.first_name}\n"
        f"<b>Фамилия:</b> {user_to_check.last_name or 'Нет'}\n"
        f"<b>Юзернейм:</b> @{user_to_check.username or 'Нет'}\n"
        f"<b>Это бот?:</b> {'Да' if user_to_check.is_bot else 'Нет'}"
    )
    
    update.message.reply_html(info_text)

def warn(update: Update, context: CallbackContext) -> None:
    """Выдает предупреждение пользователю."""
    if not is_user_admin(update, context, update.message.from_user.id):
        update.message.reply_text('Вы не являетесь администратором.')
        return
        
    if not update.message.reply_to_message:
        update.message.reply_text('Используйте эту команду в ответ на сообщение.')
        return

    user_to_warn = update.message.reply_to_message.from_user
    warner = update.message.from_user
    reason = " ".join(context.args) if context.args else "Без указания причины"

    user_mention = mention_html(user_to_warn.id, user_to_warn.first_name)
    warner_mention = mention_html(warner.id, warner.first_name)

    message = f"{user_mention}, вы получили предупреждение от {warner_mention}!\n<b>Причина:</b> {reason}"
    update.message.reply_html(message)

def kick(update: Update, context: CallbackContext) -> None:
    """Кикает пользователя (удаляет, но может вернуться)."""
    if not is_user_admin(update, context, update.message.from_user.id):
        update.message.reply_text('Вы не являетесь администратором.')
        return
        
    if not update.message.reply_to_message:
        update.message.reply_text('Используйте эту команду в ответ на сообщение.')
        return

    user_to_kick = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "Без указания причины"
    
    try:
        context.bot.kick_chat_member(chat_id=update.effective_chat.id, user_id=user_to_kick.id)
        # Сразу же разбаниваем, чтобы пользователь мог вернуться по ссылке
        context.bot.unban_chat_member(chat_id=update.effective_chat.id, user_id=user_to_kick.id)
        
        user_mention = mention_html(user_to_kick.id, user_to_kick.first_name)
        message = f"Пользователь {user_mention} был кикнут из чата.\n<b>Причина:</b> {reason}"
        update.message.reply_html(message)
    except Exception as e:
        logger.error(f"Ошибка при кике: {e}")
        update.message.reply_text(f"Не удалось кикнуть пользователя. Убедитесь, что у меня есть права администратора. Ошибка: {e}")

def mute(update: Update, context: CallbackContext) -> None:
    """Мутит пользователя на определенное время."""
    if not is_user_admin(update, context, update.message.from_user.id):
        update.message.reply_text('Вы не являетесь администратором.')
        return
        
    if not update.message.reply_to_message:
        update.message.reply_text('Используйте эту команду в ответ на сообщение.')
        return
        
    if not context.args:
        update.message.reply_text('Укажите время мута! Например: /mute 10m флуд')
        return

    duration = parse_duration(context.args[0])
    if not duration:
        update.message.reply_text('Неверный формат времени. Используйте: 10m (минуты), 2h (часы), 1d (дни).')
        return

    user_to_mute = update.message.reply_to_message.from_user
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Без указания причины"
    
    until_date = int(time.time() + duration.total_seconds())
    
    try:
        context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user_to_mute.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        user_mention = mention_html(user_to_mute.id, user_to_mute.first_name)
        message = f"Пользователь {user_mention} был заглушен на {context.args[0]}.\n<b>Причина:</b> {reason}"
        update.message.reply_html(message)
    except Exception as e:
        logger.error(f"Ошибка при муте: {e}")
        update.message.reply_text(f"Не удалось заглушить пользователя. Убедитесь, что у меня есть права. Ошибка: {e}")

def ban(update: Update, context: CallbackContext) -> None:
    """Банит пользователя навсегда."""
    if not is_user_admin(update, context, update.message.from_user.id):
        update.message.reply_text('Вы не являетесь администратором.')
        return
        
    if not update.message.reply_to_message:
        update.message.reply_text('Используйте эту команду в ответ на сообщение.')
        return

    user_to_ban = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "Без указания причины"

    try:
        context.bot.kick_chat_member(chat_id=update.effective_chat.id, user_id=user_to_ban.id)
        user_mention = mention_html(user_to_ban.id, user_to_ban.first_name)
        message = f"Пользователь {user_mention} был забанен.\n<b>Причина:</b> {reason}"
        update.message.reply_html(message)
    except Exception as e:
        logger.error(f"Ошибка при бане: {e}")
        update.message.reply_text(f"Не удалось забанить пользователя. Убедитесь, что у меня есть права. Ошибка: {e}")


def main() -> None:
    """Основная функция для запуска бота."""
    if BOT_TOKEN == 'YOUR_TOKEN':
        print("!!! ОШИБКА: Пожалуйста, вставьте ваш токен бота в переменную BOT_TOKEN в коде !!!")
        return

    updater = Updater(BOT_TOKEN)
    dispatcher = updater.dispatcher

    # Регистрируем все команды
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("info", info))
    dispatcher.add_handler(CommandHandler("warn", warn))
    dispatcher.add_handler(CommandHandler("kick", kick))
    dispatcher.add_handler(CommandHandler("mute", mute))
    dispatcher.add_handler(CommandHandler("ban", ban))

    # Запускаем бота
    updater.start_polling()
    print("Бот запущен и работает...")
    updater.idle()

if __name__ == '__main__':
    main()
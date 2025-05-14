import telebot
from telebot import types
import pandas as pd
from datetime import datetime, timedelta
import schedule
import time
import threading
import traceback
import os

# Конфигурация бота
TOKEN = ''
MAIN_ADMIN_IDS = []

bot = telebot.TeleBot(TOKEN)


# Хранилища данных в памяти
class DataStorage:
    def __init__(self):
        self.user_data = {}
        self.event_registrations = []
        self.vacancy_applications = []
        self.admins = {admin_id: 'main' for admin_id in MAIN_ADMIN_IDS}
        self.mailing_settings = {
            'enabled': True,
            'day_of_week': 6,  # 6 - воскресенье (0 - понедельник)
            'time': '12:00'
        }
        self.subscribed_users = set()
        self.parsed_messages = set()
        self.channels_to_monitor = set()
        # Добавляем новые поля для напоминаний
        self.reminder_text = None
        self.reminder_frequency = 1  # 1 - раз в неделю, 2 - раз в 2 недели, 3 - раз в 3 недели
        self.last_reminder_sent = None

storage = DataStorage()


class UserData:
    def __init__(self):
        self.name = None
        self.phone = None
        self.event_or_vacancy = None
        self.needs_pass = None
        self.about = None
        self.cv_file_id = None
        self.option = None
        self.step = None
        self.reviewing = False
        self.username = None  # Добавляем поле для username

    def get_summary(self):
        if self.option == 'event':
            return (
                f"✅ Ваша анкета на мероприятие:\n\n"
                f"📌 ФИО: {self.name}\n"
                f"👤 Username: @{self.username if self.username else 'не указан'}\n"
                f"📱 Телефон: {self.phone}\n"
                f"🎯 Мероприятие: {self.event_or_vacancy}\n"
                f"🪪 Пропуск: {'Да' if self.needs_pass else 'Нет'}"
            )
        else:
            return (
                f"✅ Ваша анкета на вакансию:\n\n"
                f"📌 ФИО: {self.name}\n"
                f"👤 Username: @{self.username if self.username else 'не указан'}\n"
                f"📱 Телефон: {self.phone}\n"
                f"💼 Вакансия: {self.event_or_vacancy}\n"
                f"📝 О себе: {self.about}\n"
                f"📎 CV: {'Прикреплено' if self.cv_file_id else 'Отсутствует'}"
            )


def is_admin(user_id) :
    return str(user_id) in storage.admins


def is_main_admin(user_id):
    return str(user_id) in MAIN_ADMIN_IDS


def schedule_mailing() :
    schedule.clear()
    if storage.mailing_settings['enabled'] :
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        day_name = days[storage.mailing_settings['day_of_week']]
        getattr(schedule.every(), day_name).at(storage.mailing_settings['time']).do(send_weekly_report)
        print(f"Рассылка запланирована на каждый {day_name} в {storage.mailing_settings['time']}")


def send_weekly_report() :
    try :
        if not storage.event_registrations :
            return

        df = pd.DataFrame(storage.event_registrations)
        week_ago = datetime.now() - timedelta(days=7)
        df['Дата регистрации'] = pd.to_datetime(df['Дата регистрации'])
        weekly_data = df[df['Дата регистрации'] >= week_ago]

        if weekly_data.empty :
            return

        filename = f"weekly_registrations_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
        weekly_data.to_excel(filename, index=False)

        for admin_id in list(storage.admins.keys()) :
            try :
                with open(filename, 'rb') as file :
                    bot.send_document(admin_id, file, caption="📊 Еженедельный отчёт по регистрациям")
            except Exception as e :
                print(f"Ошибка при отправке отчёта админу {admin_id}: {str(e)}")

        os.remove(filename)
    except Exception as e :
        print(f"Ошибка в send_weekly_report: {str(e)}")
        traceback.print_exc()


def mailing_scheduler_thread() :
    while True :
        try :
            schedule.run_pending()
            time.sleep(1)
        except Exception as e :
            print(f"Ошибка в планировщике: {str(e)}")
            time.sleep(5)


def user_menu(chat_id) :
    try :
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn1 = types.KeyboardButton('Регистрация на мероприятие')
        btn2 = types.KeyboardButton('Прислать CV для вакансии')
        markup.add(btn1, btn2)
        bot.send_message(chat_id, "👋 Привет! Это бот  мы активно делимся уникальными вакансиями, мероприятиями, а также организуем кейс-чемпионаты.\nЧто вас интересует?", reply_markup=markup)
    except Exception as e :
        handle_error(chat_id, e)


def admin_menu(message) :
    try :
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

        if is_main_admin(message.chat.id) :
            buttons = [
                '📊 Получить список регистраций',
                '📧 Управление рассылкой',
                '👥 Управление администраторами',
                '⏰ Управление напоминаниями','📢 Статус парсинга'
            ]
        else :
            buttons = ['📊 Получить список регистраций']

        for button in buttons :
            markup.add(types.KeyboardButton(button))

        bot.send_message(message.chat.id, "🛠 Панель администратора:", reply_markup=markup)
    except Exception as e :
        handle_error(message.chat.id, e)


def handle_error(chat_id, error) :
    error_msg = f"Произошла ошибка. Пожалуйста, попробуйте позже.\nОшибка: {str(error)}"
    print(error_msg)
    traceback.print_exc()
    try :
        bot.send_message(chat_id, "⚠️ Произошла ошибка. Пожалуйста, попробуйте еще раз.")
    except :
        pass


@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        if is_admin(message.chat.id):
            admin_menu(message)
        else:
            storage.subscribed_users.add(message.chat.id)
            user_menu(message.chat.id)
            # Отправляем приветственное сообщение с информацией о напоминаниях
            bot.send_message(
                message.chat.id,
                "🔔 Вы подписаны на рассылку мероприятий и напоминаний. "
                "Чтобы отписаться, используйте команду /unsubscribe"
            )
    except Exception as e:
        handle_error(message.chat.id, e)


@bot.message_handler(commands=['unsubscribe'])
def unsubscribe(message):
    try:
        if message.chat.id in storage.subscribed_users:
            storage.subscribed_users.remove(message.chat.id)
            bot.send_message(message.chat.id, "🔕 Вы отписались от рассылки мероприятий и напоминаний.")
        else:
            bot.send_message(message.chat.id, "ℹ️ Вы не подписаны на рассылку.")
    except Exception as e:
        handle_error(message.chat.id, e)


@bot.message_handler(commands=['add_channel_id'])
def add_channel_by_id(message) :
    if not is_main_admin(message.chat.id) :
        bot.reply_to(message, "❌ Эта команда доступна только главному администратору")
        return

    try :
        args = message.text.split()
        if len(args) < 2 :
            bot.reply_to(message, "❌ Укажите ID канала: /add_channel_id [ID_канала]")
            return

        channel_id = args[1]

        if not channel_id.lstrip('-').isdigit() :
            bot.reply_to(message, "❌ ID канала должен быть числом")
            return

        channel_id = int(channel_id)

        try :
            chat = bot.get_chat(channel_id)
            if chat.type != 'channel' :
                bot.reply_to(message, "❌ Указанный ID не является каналом")
                return

            chat_member = bot.get_chat_member(channel_id, bot.get_me().id)
            if chat_member.status not in ['administrator', 'creator'] :
                bot.reply_to(message, "❌ Бот не является администратором этого канала")
                return

            storage.channels_to_monitor.add(channel_id)
            bot.reply_to(message, f"✅ Канал {chat.title} (ID: {channel_id}) добавлен для мониторинга")
        except Exception as e :
            bot.reply_to(message, f"❌ Ошибка: {str(e)}")
    except Exception as e :
        handle_error(message.chat.id, e)


@bot.message_handler(commands=['add_channel'])
def add_channel(message) :
    if not is_main_admin(message.chat.id) :
        bot.reply_to(message, "❌ Эта команда доступна только главному администратору")
        return

    try :
        if message.forward_from_chat and message.forward_from_chat.type == 'channel' :
            channel_id = message.forward_from_chat.id

            try :
                chat_member = bot.get_chat_member(channel_id, bot.get_me().id)
                if chat_member.status not in ['administrator', 'creator'] :
                    bot.reply_to(message, "❌ Бот не является администратором этого канала")
                    return

                storage.channels_to_monitor.add(channel_id)
                bot.reply_to(message,
                             f"✅ Канал {message.forward_from_chat.title} (ID: {channel_id}) добавлен для мониторинга")
            except Exception as e :
                bot.reply_to(message, f"❌ Ошибка при проверке прав бота: {str(e)}")
        else :
            bot.reply_to(message, "❌ Перешлите сообщение из канала или используйте /add_channel_id [ID_канала]")
    except Exception as e :
        handle_error(message.chat.id, e)


@bot.message_handler(commands=['remove_channel'])
def remove_channel(message) :
    if not is_main_admin(message.chat.id) :
        bot.reply_to(message, "❌ Эта команда доступна только главному администратору")
        return

    try :
        if not storage.channels_to_monitor :
            bot.reply_to(message, "ℹ️ Нет отслеживаемых каналов")
            return

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for channel_id in storage.channels_to_monitor :
            try :
                chat = bot.get_chat(channel_id)
                markup.add(f"{chat.title} (ID: {channel_id})")
            except :
                markup.add(f"ID: {channel_id}")
        markup.add('❌ Отмена')

        msg = bot.reply_to(message, "Выберите канал для удаления из мониторинга:", reply_markup=markup)
        bot.register_next_step_handler(msg, process_remove_channel)
    except Exception as e :
        handle_error(message.chat.id, e)


def process_remove_channel(message) :
    try :
        if message.text == '❌ Отмена' :
            bot.send_message(message.chat.id, "❌ Отмена", reply_markup=types.ReplyKeyboardRemove())
            return

        channel_id = None
        if '(' in message.text and ')' in message.text :
            id_part = message.text.split('(')[1].split(')')[0]
            if id_part.startswith('ID: ') :
                channel_id = int(id_part[4 :])
        elif message.text.startswith('ID: ') :
            channel_id = int(message.text[4 :])

        if channel_id is None or channel_id not in storage.channels_to_monitor :
            bot.send_message(message.chat.id, "❌ Неверный выбор канала", reply_markup=types.ReplyKeyboardRemove())
            return

        storage.channels_to_monitor.remove(channel_id)
        bot.send_message(message.chat.id, f"✅ Канал удален из мониторинга", reply_markup=types.ReplyKeyboardRemove())
    except Exception as e :
        handle_error(message.chat.id, e)


@bot.message_handler(func=lambda m : m.text == '📢 Статус парсинга' and is_main_admin(m.chat.id))
def chat_monitoring_status(message) :
    try :
        status = "🟢 Активен"
        text = f"📢 Статус парсинга:\n\n{status}\n\n"
        text += f"Подписчиков на рассылку: {len(storage.subscribed_users)}\n"
        text += f"Отслеживаемых каналов: {len(storage.channels_to_monitor)}\n\n"

        if storage.channels_to_monitor :
            text += "Список отслеживаемых каналов:\n"
            for channel_id in storage.channels_to_monitor :
                try :
                    chat = bot.get_chat(channel_id)
                    text += f"- {chat.title} (ID: {channel_id})\n"
                except Exception as e :
                    text += f"- ID: {channel_id} (не удалось получить информацию)\n"

        text += "\nДля добавления канала:\n1. Перешлите любое сообщение из канала и отправьте /add_channel\n2. Или отправьте команду /add_channel_id [ID_канала]\n\nДля удаления канала используйте /remove_channel"

        bot.send_message(message.chat.id, text)
    except Exception as e :
        handle_error(message.chat.id, e)

@bot.message_handler(func=lambda m: m.text == '⏰ Управление напоминаниями' and is_main_admin(m.chat.id))
def reminder_settings_menu(message):
    try:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('📝 Установить текст напоминания', '🔄 Изменить частоту')
        markup.add('👁 Просмотреть текущие настройки', '⬅️ Назад')

        bot.send_message(
            message.chat.id,
            "⏰ Меню управления напоминаниями:",
            reply_markup=markup
        )
    except Exception as e:
        handle_error(message.chat.id, e)


@bot.message_handler(func=lambda m : m.text in ['📝 Установить текст напоминания', '🔄 Изменить частоту',
                                                '👁 Просмотреть текущие настройки', '⬅️ Назад']
                                     and is_main_admin(m.chat.id))
def handle_reminder_settings(message) :
    try :
        if message.text == '📝 Установить текст напоминания' :
            msg = bot.send_message(
                message.chat.id,
                "✏️ Введите текст напоминания:",
                reply_markup=types.ReplyKeyboardRemove()
            )
            bot.register_next_step_handler(msg, process_reminder_text)

        elif message.text == '🔄 Изменить частоту' :
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add('1 неделя', '2 недели', '3 недели')
            markup.add('❌ Отмена')
            msg = bot.send_message(
                message.chat.id,
                "Выберите частоту отправки напоминаний:",
                reply_markup=markup
            )
            bot.register_next_step_handler(msg, process_reminder_frequency)

        elif message.text == '👁 Просмотреть текущие настройки' :
            frequency_text = {
                1 : "1 неделя",
                2 : "2 недели",
                3 : "3 недели"
            }.get(storage.reminder_frequency, "Не установлено")

            text = (
                f"⏰ Текущие настройки напоминаний:\n\n"
                f"📝 Текст: {storage.reminder_text if storage.reminder_text else 'Не установлен'}\n"
                f"🔄 Частота: {frequency_text}\n"
                f"📅 Последняя отправка: {storage.last_reminder_sent.strftime('%Y-%m-%d %H:%M') if storage.last_reminder_sent else 'Еще не отправлялось'}"
            )
            bot.send_message(message.chat.id, text)

        elif message.text == '⬅️ Назад' :
            admin_menu(message)
    except Exception as e :
        handle_error(message.chat.id, e)


def process_reminder_text(message) :
    try :
        storage.reminder_text = message.text
        bot.send_message(
            message.chat.id,
            "✅ Текст напоминания сохранен",
            reply_markup=types.ReplyKeyboardRemove()
        )
        reminder_settings_menu(message)
    except Exception as e :
        handle_error(message.chat.id, e)


def process_reminder_frequency(message) :
    try :
        if message.text == '❌ Отмена' :
            reminder_settings_menu(message)
            return

        if message.text == '1 неделя' :
            storage.reminder_frequency = 1
        elif message.text == '2 недели' :
            storage.reminder_frequency = 2
        elif message.text == '3 недели' :
            storage.reminder_frequency = 3
        else :
            bot.send_message(message.chat.id, "❌ Неверный выбор")
            reminder_settings_menu(message)
            return

        bot.send_message(
            message.chat.id,
            f"✅ Частота напоминаний установлена: {message.text}",
            reply_markup=types.ReplyKeyboardRemove()
        )
        reminder_settings_menu(message)
    except Exception as e :
        handle_error(message.chat.id, e)

def send_reminders():
    try:
        if not storage.reminder_text or not storage.subscribed_users:
            return

        # Проверяем, нужно ли отправлять напоминание
        if storage.last_reminder_sent:
            delta = datetime.now() - storage.last_reminder_sent
            days_needed = storage.reminder_frequency * 7
            if delta.days < days_needed:
                return

        # Отправляем напоминания
        for user_id in storage.subscribed_users:
            try:
                bot.send_message(
                    user_id,
                    f"⏰ Напоминание:\n\n{storage.reminder_text}"
                )
            except Exception as e:
                print(f"Ошибка при отправке напоминания пользователю {user_id}: {str(e)}")
                storage.subscribed_users.discard(user_id)

        storage.last_reminder_sent = datetime.now()
        print(f"Напоминания отправлены {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    except Exception as e:
        print(f"Ошибка в send_reminders: {str(e)}")
        traceback.print_exc()

def mailing_scheduler_thread():
    while True:
        try:
            schedule.run_pending()
            send_reminders()  # Добавляем вызов функции отправки напоминаний
            time.sleep(1)
        except Exception as e:
            print(f"Ошибка в планировщике: {str(e)}")
            time.sleep(5)

def show_review_menu(chat_id, message_text) :
    try :
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('✅ Отправить', '✏️ Редактировать')
        msg = bot.send_message(
            chat_id,
            message_text,
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_review_step)
    except Exception as e :
        handle_error(chat_id, e)


def process_review_step(message) :
    try :
        chat_id = message.chat.id
        if chat_id not in storage.user_data :
            bot.send_message(chat_id, "⌛️ Сессия устарела. Начните заново с /start")
            return

        user = storage.user_data[chat_id]

        if message.text == '✅ Отправить' :
            if user.option == 'event' :
                complete_event_registration(chat_id)
            else :
                complete_vacancy_application(chat_id)
        elif message.text == '✏️ Редактировать' :
            user.reviewing = True
            show_edit_menu(chat_id)
        else :
            bot.send_message(chat_id, "⚠️ Пожалуйста, используйте кнопки")
            show_review_menu(chat_id, user.get_summary())
    except Exception as e :
        handle_error(chat_id, e)


def show_edit_menu(chat_id):
    try:
        user = storage.user_data[chat_id]
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

        if user.option == 'event':
            buttons = [
                '✏️ Изменить ФИО', '📱 Изменить телефон',
                '🎯 Изменить мероприятие', '🪪 Изменить пропуск',
                '👤 Изменить username'
            ]
        else:
            buttons = [
                '✏️ Изменить ФИО', '📱 Изменить телефон',
                '💼 Изменить вакансию', '📝 Изменить информацию о себе',
                '📎 Изменить CV', '👤 Изменить username'
            ]

        for button in buttons:
            markup.add(button)

        markup.add('⬅️ Назад к просмотру')

        msg = bot.send_message(
            chat_id,
            "🔧 Что вы хотите изменить?",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, handle_edit_selection)
    except Exception as e:
        handle_error(chat_id, e)

def handle_edit_selection(message):
    try:
        chat_id = message.chat.id
        user = storage.user_data[chat_id]

        if message.text == '⬅️ Назад к просмотру':
            user.reviewing = False
            show_review_menu(chat_id, user.get_summary())
            return

        if 'ФИО' in message.text:
            user.step = 'edit_name'
            msg = bot.send_message(chat_id, "✏️ Введите новое ФИО:", reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, process_edit_step)
        elif 'телефон' in message.text:
            user.step = 'edit_phone'
            msg = bot.send_message(chat_id, "📱 Введите новый телефон:", reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, process_edit_step)
        elif 'мероприятие' in message.text:
            user.step = 'edit_event'
            msg = bot.send_message(chat_id, "🎯 Введите новое мероприятие:", reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, process_edit_step)
        elif 'вакансию' in message.text:
            user.step = 'edit_vacancy'
            msg = bot.send_message(chat_id, "💼 Введите новую вакансию:", reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, process_edit_step)
        elif 'информацию о себе' in message.text:
            user.step = 'edit_about'
            msg = bot.send_message(chat_id, "📝 Введите новую информацию о себе:",
                                   reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, process_edit_step)
        elif 'пропуск' in message.text:
            user.step = 'edit_pass'
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add('Да', 'Нет')
            msg = bot.send_message(chat_id, "🪪 Нужен ли вам пропуск?", reply_markup=markup)
            bot.register_next_step_handler(msg, process_edit_step)
        elif 'CV' in message.text:
            user.step = 'edit_cv'
            msg = bot.send_message(chat_id, "📎 Прикрепите новое CV (файл PDF или DOCX):",
                                   reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, process_edit_step)
        elif 'username' in message.text:
            user.step = 'edit_username'
            msg = bot.send_message(chat_id, "👤 Введите новый username (без @):",
                                   reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, process_edit_step)
        else:
            bot.send_message(chat_id, "⚠️ Неверный выбор")
            show_edit_menu(chat_id)
    except Exception as e:
        handle_error(chat_id, e)

def process_edit_step(message):
    try:
        chat_id = message.chat.id
        user = storage.user_data[chat_id]

        if user.step == 'edit_name':
            user.name = message.text
        elif user.step == 'edit_phone':
            user.phone = message.text
        elif user.step == 'edit_event':
            user.event_or_vacancy = message.text
        elif user.step == 'edit_vacancy':
            user.event_or_vacancy = message.text
        elif user.step == 'edit_about':
            user.about = message.text
        elif user.step == 'edit_pass':
            user.needs_pass = message.text.lower() in ['да', 'yes']
        elif user.step == 'edit_cv':
            if message.document:
                user.cv_file_id = message.document.file_id
            else:
                msg = bot.send_message(chat_id, "⚠️ Пожалуйста, прикрепите файл")
                bot.register_next_step_handler(msg, process_edit_step)
                return
        elif user.step == 'edit_username':
            username = message.text.strip()
            if username.startswith('@'):
                username = username[1:]
            user.username = username if username else None

        user.reviewing = False
        show_review_menu(chat_id, user.get_summary())
    except Exception as e:
        handle_error(chat_id, e)


@bot.message_handler(func=lambda m: m.text == 'Регистрация на мероприятие' and not is_admin(m.chat.id))
def start_event_registration(message):
    try:
        storage.user_data[message.chat.id] = UserData()
        storage.user_data[message.chat.id].option = 'event'
        storage.user_data[message.chat.id].step = 'name'
        # Сохраняем username, если он есть
        storage.user_data[message.chat.id].username = message.from_user.username
        msg = bot.reply_to(message, "✏️ Введите ваше ФИО:", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, process_name_step)
    except Exception as e:
        handle_error(message.chat.id, e)



def process_name_step(message) :
    try :
        chat_id = message.chat.id
        storage.user_data[chat_id].name = message.text
        storage.user_data[chat_id].step = 'phone'
        msg = bot.reply_to(message, "📱 Введите ваш номер телефона:")
        bot.register_next_step_handler(msg, process_phone_step)
    except Exception as e :
        handle_error(message.chat.id, e)


def process_phone_step(message) :
    try :
        chat_id = message.chat.id
        storage.user_data[chat_id].phone = message.text

        if storage.user_data[chat_id].option == 'event' :
            storage.user_data[chat_id].step = 'event'
            msg = bot.reply_to(message, "🎯 Пожалуйста, введите название мероприятия, на которое хотите зарегистрироваться (можно ориентироваться на название, указанное в посте канала):")
            bot.register_next_step_handler(msg, process_event_step)
        else :
            storage.user_data[chat_id].step = 'vacancy'
            msg = bot.reply_to(message, "💼 Пожалуйста, введите название вакансии, которая вас интересует (можно ориентироваться на название, указанное в посте канала):")
            bot.register_next_step_handler(msg, process_vacancy_step)
    except Exception as e :
        handle_error(message.chat.id, e)


def process_event_step(message) :
    try :
        chat_id = message.chat.id
        storage.user_data[chat_id].event_or_vacancy = message.text
        storage.user_data[chat_id].step = 'pass'

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('Да', 'Нет')
        msg = bot.reply_to(message, "🪪 Нужен ли вам пропуск в НИУ ВШЭ?\nВыберите нет, если мероприятие онлайн", reply_markup=markup)
        bot.register_next_step_handler(msg, process_pass_step)
    except Exception as e :
        handle_error(message.chat.id, e)


def process_pass_step(message) :
    try :
        chat_id = message.chat.id
        storage.user_data[chat_id].needs_pass = message.text.lower() in ['да', 'yes']
        show_review_menu(chat_id, storage.user_data[chat_id].get_summary())
    except Exception as e :
        handle_error(message.chat.id, e)


@bot.message_handler(func=lambda m: m.text == 'Прислать CV для вакансии' and not is_admin(m.chat.id))
def start_vacancy_application(message):
    try:
        storage.user_data[message.chat.id] = UserData()
        storage.user_data[message.chat.id].option = 'vacancy'
        storage.user_data[message.chat.id].step = 'name'
        # Сохраняем username, если он есть
        storage.user_data[message.chat.id].username = message.from_user.username
        msg = bot.reply_to(message, "✏️ Введите ваше ФИО:", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, process_name_step)
    except Exception as e:
        handle_error(message.chat.id, e)


def process_vacancy_step(message) :
    try :
        chat_id = message.chat.id
        storage.user_data[chat_id].event_or_vacancy = message.text
        storage.user_data[chat_id].step = 'about'
        msg = bot.reply_to(message, "📝 Пожалуйста, напишите несколько предложений, почему вас интересует данная вакансия и почему вы считаете себя подходящим кандидатом:")
        bot.register_next_step_handler(msg, process_about_step)
    except Exception as e :
        handle_error(message.chat.id, e)


def process_about_step(message) :
    try :
        chat_id = message.chat.id
        storage.user_data[chat_id].about = message.text
        storage.user_data[chat_id].step = 'cv'
        msg = bot.reply_to(message, "📎 Прикрепите ваше CV (файл PDF или DOCX):")
        bot.register_next_step_handler(msg, process_cv_step)
    except Exception as e :
        handle_error(message.chat.id, e)


def process_cv_step(message) :
    try :
        chat_id = message.chat.id
        if message.document :
            storage.user_data[chat_id].cv_file_id = message.document.file_id
            show_review_menu(chat_id, storage.user_data[chat_id].get_summary())
        else :
            msg = bot.reply_to(message, "⚠️ Пожалуйста, отправьте файл")
            bot.register_next_step_handler(msg, process_cv_step)
    except Exception as e :
        handle_error(message.chat.id, e)


def complete_event_registration(chat_id):
    try:
        user = storage.user_data[chat_id]

        registration_data = {
            'ФИО': user.name,
            'Username': f"@{user.username}" if user.username else "не указан",
            'Телефон': user.phone,
            'Мероприятие': user.event_or_vacancy,
            'Пропуск': 'Да' if user.needs_pass else 'Нет',
            'Дата регистрации': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        storage.event_registrations.append(registration_data)

        bot.send_message(
            chat_id,
            f"🎉 Спасибо за регистрацию!\n\n{user.get_summary()}",
            reply_markup=types.ReplyKeyboardRemove()
        )

        for admin_id in list(storage.admins.keys()):
            try:
                bot.send_message(
                    admin_id,
                    f"📝 Спасибо, мы зарегистрировали вас на мероприятие! ✅\nЗа всеми обновлениями вы можете следить в канале https://t.me/hsecareercenter:\n"
                    f"👤 ФИО: {user.name}\n"
                    f"👤 Username: @{user.username if user.username else 'не указан'}\n"
                    f"📱 Телефон: {user.phone}\n"
                    f"🎯 Мероприятие: {user.event_or_vacancy}\n"
                    f"🪪 Пропуск: {'Да' if user.needs_pass else 'Нет'}"
                )
            except Exception as e:
                print(f"Ошибка при отправке уведомления админу {admin_id}: {str(e)}")

        del storage.user_data[chat_id]
        user_menu(chat_id)
    except Exception as e:
        handle_error(chat_id, e)

def complete_vacancy_application(chat_id):
    try:
        user = storage.user_data[chat_id]

        application_data = {
            'ФИО': user.name,
            'Username': f"@{user.username}" if user.username else "не указан",
            'Телефон': user.phone,
            'Вакансия': user.event_or_vacancy,
            'О себе': user.about,
            'Дата подачи': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        storage.vacancy_applications.append(application_data)

        bot.send_message(
            chat_id,
            f"🎉 Спасибо за ваше резюме!\n\n{user.get_summary()}",
            reply_markup=types.ReplyKeyboardRemove()
        )

        for admin_id in list(storage.admins.keys()):
            try:
                bot.send_message(
                    admin_id,
                    f"📄 Спасибо! Мы приняли вашу заявку на вакансию! В случае, если ваша кандидатура заинтересует работодателя, мы обязательно с вами свяжемся ✅:\n"
                    f"👤 ФИО: {user.name}\n"
                    f"👤 Username: @{user.username if user.username else 'не указан'}\n"
                    f"📱 Телефон: {user.phone}\n"
                    f"💼 Вакансия: {user.event_or_vacancy}\n"
                    f"📝 О себе: {user.about}"
                )
                if user.cv_file_id:
                    bot.send_document(admin_id, user.cv_file_id)
            except Exception as e:
                print(f"Ошибка при отправке уведомления админу {admin_id}: {str(e)}")

        del storage.user_data[chat_id]
        user_menu(chat_id)
    except Exception as e:
        handle_error(chat_id, e)


def complete_vacancy_application(chat_id) :
    try :
        user = storage.user_data[chat_id]

        application_data = {
            'ФИО' : user.name,
            'Телефон' : user.phone,
            'Username' : f"@{user.username}" if user.username else "не указан",
            'Вакансия' : user.event_or_vacancy,
            'О себе' : user.about,
            'Дата подачи' : datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        storage.vacancy_applications.append(application_data)

        bot.send_message(
            chat_id,
            f"🎉 Спасибо за ваше резюме!\n\n{user.get_summary()}",
            reply_markup=types.ReplyKeyboardRemove()
        )

        for admin_id in list(storage.admins.keys()) :
            try :
                bot.send_message(
                    admin_id,
                    f"📄 Новая заявка на вакансию:\n"
                    f"👤 ФИО: {user.name}\n"
                    f"📱 Телефон: {user.phone}\n"
                    f"👤 Username: @{user.username if user.username else 'не указан'}\n"
                    f"💼 Вакансия: {user.event_or_vacancy}\n"
                    f"📝 О себе: {user.about}"
                )
                if user.cv_file_id :
                    bot.send_document(admin_id, user.cv_file_id)
            except Exception as e :
                print(f"Ошибка при отправке уведомления админу {admin_id}: {str(e)}")

        del storage.user_data[chat_id]
        user_menu(chat_id)
    except Exception as e :
        handle_error(chat_id, e)


@bot.message_handler(func=lambda m : m.text == '📊 Получить список регистраций' and is_admin(m.chat.id))
def send_excel_report(message) :
    try :
        if not storage.event_registrations :
            bot.send_message(message.chat.id, "ℹ️ Нет данных о регистрациях")
            return

        filename = f"registrations_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        pd.DataFrame(storage.event_registrations).to_excel(filename, index=False)

        with open(filename, 'rb') as file :
            bot.send_document(message.chat.id, file, caption="📊 Список регистраций")

        os.remove(filename)
    except Exception as e :
        handle_error(message.chat.id, e)


@bot.message_handler(func=lambda m : m.text == '📧 Управление рассылкой' and is_main_admin(m.chat.id))
def mailing_settings_menu(message) :
    try :
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('🔘 Включить/выключить рассылку', '📅 Изменить день рассылки')
        markup.add('⏰ Изменить время рассылки', '⬅️ Назад')

        status = "включена" if storage.mailing_settings['enabled'] else "выключена"
        days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
        day = days[storage.mailing_settings['day_of_week']]

        text = f"📧 Текущие настройки рассылки:\n\n🔘 Статус: {status}\n📅 День: {day}\n⏰ Время: {storage.mailing_settings['time']}"
        bot.send_message(message.chat.id, text, reply_markup=markup)
    except Exception as e :
        handle_error(message.chat.id, e)


@bot.message_handler(func=lambda m : m.text in ['🔘 Включить/выключить рассылку', '📅 Изменить день рассылки',
                                                '⏰ Изменить время рассылки', '⬅️ Назад'] and is_main_admin(m.chat.id))
def handle_mailing_settings(message) :
    try :
        if message.text == '🔘 Включить/выключить рассылку' :
            storage.mailing_settings['enabled'] = not storage.mailing_settings['enabled']
            schedule_mailing()
            status = "включена" if storage.mailing_settings['enabled'] else "выключена"
            bot.send_message(message.chat.id, f"✅ Рассылка теперь {status}")
            mailing_settings_menu(message)

        elif message.text == '📅 Изменить день рассылки' :
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
            for day in days :
                markup.add(day)
            markup.add('❌ Отмена')
            msg = bot.send_message(message.chat.id, "Выберите новый день для рассылки:", reply_markup=markup)
            bot.register_next_step_handler(msg, process_day_change)

        elif message.text == '⏰ Изменить время рассылки' :
            msg = bot.send_message(message.chat.id, "Введите новое время в формате ЧЧ:ММ (например, 14:30):",
                                   reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, process_time_change)

        elif message.text == '⬅️ Назад' :
            admin_menu(message)
    except Exception as e :
        handle_error(message.chat.id, e)


def process_day_change(message) :
    try :
        if message.text == '❌ Отмена' :
            mailing_settings_menu(message)
            return

        days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
        if message.text in days :
            storage.mailing_settings['day_of_week'] = days.index(message.text)
            schedule_mailing()
            bot.send_message(message.chat.id, f"✅ День рассылки изменён на {message.text}")
        else :
            bot.send_message(message.chat.id, "❌ Неверный день")

        mailing_settings_menu(message)
    except Exception as e :
        handle_error(message.chat.id, e)


def process_time_change(message) :
    try :
        time_str = message.text
        datetime.strptime(time_str, '%H:%M')
        storage.mailing_settings['time'] = time_str
        schedule_mailing()
        bot.send_message(message.chat.id, f"✅ Время рассылки изменено на {time_str}")
        mailing_settings_menu(message)
    except ValueError :
        bot.send_message(message.chat.id, "❌ Неверный формат времени. Используйте ЧЧ:ММ")
        mailing_settings_menu(message)
    except Exception as e :
        handle_error(message.chat.id, e)


@bot.message_handler(func=lambda m : m.text == '👥 Управление администраторами' and is_main_admin(m.chat.id))
def admins_management_menu(message) :
    try :
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('➕ Добавить администратора', '➖ Удалить администратора')
        markup.add('📋 Список администраторов', '⬅️ Назад')
        bot.send_message(message.chat.id, "👥 Управление администраторами:", reply_markup=markup)
    except Exception as e :
        handle_error(message.chat.id, e)


@bot.message_handler(func=lambda m : m.text in ['➕ Добавить администратора', '➖ Удалить администратора',
                                                '📋 Список администраторов', '⬅️ Назад'] and is_main_admin(m.chat.id))
def handle_admin_management(message) :
    try :
        if message.text == '➕ Добавить администратора' :
            msg = bot.send_message(message.chat.id, "Введите ID нового администратора(можно посмотреть тут https://t.me/username_to_id_bot):",
                                   reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(msg, process_add_admin)

        elif message.text == '➖ Удалить администратора' :
            if len(storage.admins) <= 1 :
                bot.send_message(message.chat.id, "❌ Нельзя удалить всех администраторов")
                return

            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            for admin_id in storage.admins :
                if message.text in storage.admins and str(message.text) not in MAIN_ADMIN_IDS:
                    markup.add(admin_id)
            markup.add('❌ Отмена')
            msg = bot.send_message(message.chat.id, "Выберите администратора для удаления:", reply_markup=markup)
            bot.register_next_step_handler(msg, process_remove_admin)

        elif message.text == '📋 Список администраторов' :
            text = "👥 Список администраторов:\n\n"
            for admin_id, admin_type in storage.admins.items() :
                text += f"{admin_id} ({'главный' if admin_type == 'main' else 'обычный'})\n"
            bot.send_message(message.chat.id, text)

        elif message.text == '⬅️ Назад' :
            admin_menu(message)
    except Exception as e :
        handle_error(message.chat.id, e)


def process_add_admin(message) :
    try :
        new_admin_id = message.text.strip()
        if not new_admin_id.isdigit() :
            bot.send_message(message.chat.id, "❌ ID должен состоять только из цифр")
            return

        if new_admin_id in storage.admins :
            bot.send_message(message.chat.id, "⚠️ Этот пользователь уже администратор")
        else :
            storage.admins[new_admin_id] = 'regular'
            bot.send_message(message.chat.id, f"✅ Пользователь {new_admin_id} добавлен как администратор")

        admins_management_menu(message)
    except Exception as e :
        handle_error(message.chat.id, e)


def process_remove_admin(message) :
    try :
        if message.text == '❌ Отмена' :
            admins_management_menu(message)
            return

        if message.text in storage.admins and message.text != MAIN_ADMIN_IDS :
            del storage.admins[message.text]
            bot.send_message(message.chat.id, f"✅ Администратор {message.text} удалён")
        else :
            bot.send_message(message.chat.id, "❌ Неверный выбор администратора")

        admins_management_menu(message)
    except Exception as e :
        handle_error(message.chat.id, e)


@bot.channel_post_handler(content_types=['text', 'photo', 'document', 'video'])
def handle_channel_post(message) :
    try :
        print(f"Получено сообщение из канала {message.chat.id} ({message.chat.title})")

        # Проверяем, что канал в списке для мониторинга
        if message.chat.id not in storage.channels_to_monitor :
            print(f"Канал {message.chat.id} не в списке мониторинга")
            return

        # Проверяем, что сообщение еще не обрабатывалось
        if message.message_id in storage.parsed_messages :
            print(f"Сообщение {message.message_id} уже обработано")
            return

        storage.parsed_messages.add(message.message_id)

        # Формируем текст сообщения
        text = message.text if message.text else message.caption if message.caption else "📢 Новое сообщение из канала"

        # Создаем кнопку для регистрации
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton('Записаться на мероприятие', callback_data='register_from_chat'))

        # Рассылаем подписчикам
        for user_id in storage.subscribed_users :
            try :
                if message.photo :
                    bot.send_photo(
                        user_id,
                        message.photo[-1].file_id,
                        caption=f"{text}\n\n📍 Канал: {message.chat.title}",
                        reply_markup=markup
                    )
                elif message.document :
                    bot.send_document(
                        user_id,
                        message.document.file_id,
                        caption=f"{text}\n\n📍 Канал: {message.chat.title}",
                        reply_markup=markup
                    )
                elif message.video :
                    bot.send_video(
                        user_id,
                        message.video.file_id,
                        caption=f"{text}\n\n📍 Канал: {message.chat.title}",
                        reply_markup=markup
                    )
                else :
                    bot.send_message(
                        user_id,
                        f"📢 Сообщение из канала '{message.chat.title}':\n\n{text}",
                        reply_markup=markup
                    )
                print(f"Сообщение отправлено пользователю {user_id}")
            except Exception as e :
                print(f"Ошибка при отправке сообщения пользователю {user_id}: {str(e)}")
                storage.subscribed_users.discard(user_id)

        # Очищаем старые ID сообщений
        if len(storage.parsed_messages) > 1000 :
            oldest = sorted(storage.parsed_messages)[:100]
            storage.parsed_messages = set(sorted(storage.parsed_messages)[100 :])

        print("Сообщение успешно обработано")
    except Exception as e :
        print(f"Ошибка при обработке сообщения из канала: {str(e)}")
        traceback.print_exc()


@bot.message_handler(content_types=['text', 'photo', 'document', 'video'],
                     func=lambda m : m.chat.type in ['group', 'supergroup'])
def handle_group_messages(message) :
    try :
        print(f"Получено сообщение из группы {message.chat.id} ({message.chat.title})")

        # Проверяем, что бот админ в этом чате
        try :
            chat_member = bot.get_chat_member(message.chat.id, bot.get_me().id)
            if chat_member.status not in ['administrator', 'creator'] :
                print(f"Бот не админ в чате {message.chat.id}")
                return
        except Exception as e :
            print(f"Ошибка при проверке прав бота в чате {message.chat.id}: {str(e)}")
            return

        # Проверяем, что сообщение еще не обрабатывалось
        if message.message_id in storage.parsed_messages :
            print(f"Сообщение {message.message_id} уже обработано")
            return

        storage.parsed_messages.add(message.message_id)

        # Формируем текст сообщения
        text = message.text if message.text else message.caption if message.caption else "📢 Новое сообщение"



        # Рассылаем подписчикам
        for user_id in storage.subscribed_users :
            try :
                if message.photo :
                    bot.send_photo(
                        user_id,
                        message.photo[-1].file_id,
                        caption=f"{text}\n\n📍 Чат: {message.chat.title}",
                    )
                elif message.document :
                    bot.send_document(
                        user_id,
                        message.document.file_id,
                        caption=f"{text}\n\n📍 Чат: {message.chat.title}",
                                            )
                elif message.video :
                    bot.send_video(
                        user_id,
                        message.video.file_id,
                        caption=f"{text}\n\n📍 Чат: {message.chat.title}",
                                            )
                else :
                    bot.send_message(
                        user_id,
                        f"📢 Сообщение из чата '{message.chat.title}':\n\n{text}",
                                        )
                print(f"Сообщение отправлено пользователю {user_id}")
            except Exception as e :
                print(f"Ошибка при отправке сообщения пользователю {user_id}: {str(e)}")
                storage.subscribed_users.discard(user_id)

        # Очищаем старые ID сообщений
        if len(storage.parsed_messages) > 1000 :
            oldest = sorted(storage.parsed_messages)[:100]
            storage.parsed_messages = set(sorted(storage.parsed_messages)[100 :])

        print("Сообщение успешно обработано")
    except Exception as e :
        print(f"Ошибка при обработке сообщения из чата: {str(e)}")
        traceback.print_exc()


@bot.callback_query_handler(func=lambda call : call.data == 'register_from_chat')
def handle_register_from_chat(call) :
    try :
        bot.answer_callback_query(call.id)
        start_event_registration(call.message)
    except Exception as e :
        handle_error(call.message.chat.id, e)


@bot.message_handler(func=lambda message : True)
def handle_unknown(message) :
    try :
        if message.chat.id in storage.user_data and storage.user_data[message.chat.id].reviewing :
            return

        if is_admin(message.chat.id) :
            if message.text in ['📊 Получить список регистраций', '📧 Управление рассылкой',
                                '👥 Управление администраторами', '📢 Статус парсинга'] :
                return
            bot.send_message(message.chat.id, "ℹ️ Используйте кнопки меню администратора")
        else :
            bot.send_message(message.chat.id, "ℹ️ Используйте кнопки меню или /start")
    except Exception as e :
        handle_error(message.chat.id, e)


if __name__ == '__main__' :
    # Добавим тестовый канал при запуске (можно удалить)
    TEST_CHANNEL_ID =  # Замените на реальный ID вашего канала
    storage.channels_to_monitor.add(TEST_CHANNEL_ID)
    print(f"Добавлен тестовый канал для мониторинга: {TEST_CHANNEL_ID}")

    schedule_mailing()

    scheduler_thread = threading.Thread(target=mailing_scheduler_thread)
    scheduler_thread.daemon = True
    scheduler_thread.start()

    print("Бот запущен...")
    try :
        bot.infinity_polling()
    except Exception as e :
        print(f"Ошибка в основном потоке: {str(e)}")
        traceback.print_exc()
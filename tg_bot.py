import telebot
from telebot import types
import conf
import sqlite3
import markovify
import random

bot = telebot.TeleBot(conf.TOKEN)
name = None

# загрузка текста
with open("all_tolstoy.txt", encoding="utf-8") as f:
    text = f.read()

# создание модели markovify на основе текста
text_model = markovify.Text(text)


# функция при вызове команды /start, предлагает нажать на 1 из кнопок
@bot.message_handler(commands=['start'])
def main(message):
    markup = types.InlineKeyboardMarkup()
    # кнопка, которая запускает функцию, в которой объясняются правила
    markup.add(types.InlineKeyboardButton('Правила игры', callback_data='rules'))
    # кнопка переносит на сайт с объяснением, как работает генерация текста
    markup.add(types.InlineKeyboardButton('Как это работает?', url='https://thecode.media/markov-chain/'))

    bot.send_message(message.chat.id, f'Здравствуйте! Вы попали в игру "Толстой или компьютер?", '
                                      f'в которой вам нужно угадать, написано ли предложение Л.Н. Толстым '
                                      f'или сгенерировано компьютером! Удачи! (чтобы подробнее ознакомиться с '
                                      f'правилами и начать игру, нажмите кнопку "Правила")', reply_markup=markup)

    # создаем базу данных
    conn = sqlite3.connect('results.sql')
    cur = conn.cursor()

    cur.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, score INTEGER DEFAULT 0)')
    conn.commit()
    cur.close()
    conn.close()


@bot.callback_query_handler(func=lambda callback: callback.data == 'rules')  # функция с правилами игры
def callback_message(callback):
    bot.send_message(callback.message.chat.id, 'В чате будут выводиться предложения, ваша задача - угадать, является ли'
                                               ' это предложение оригинальным из произведения Льва Николаевича Толстого'
                                               ' или сгенерированным с помощью модели. Напишите "Толстой", если '
                                               'считаете, что предложение принадлежит автору, или "Компьютер", если '
                                               'считаете, что предложение создал компьютер. Перед тем как начать, '
                                               'пожалуйста, расскажите немного о себе!')
    bot.send_message(callback.message.chat.id, '1) Введите имя или псевдоним')
    bot.register_next_step_handler_by_chat_id(callback.message.chat.id, user_name)


def user_name(message):
    global name
    name = message.text.strip()
    bot.send_message(message.chat.id, "2) Часто ли вы читаете Толстого? Напишите 'да' или 'нет'")
    bot.register_next_step_handler(message, reading)


# заносим ответ в базу данных, пользователю выводится кнопка "начать"
def reading(message):
    read = message.text.strip()

    conn = sqlite3.connect('results.sql')
    cur = conn.cursor()

    # добавляем новую запись о пользователе
    cur.execute("INSERT INTO users (name, score) VALUES (?, 0)", (name,))
    conn.commit()
    cur.close()
    conn.close()

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('Начать', callback_data='game'))

    if read.lower() == 'да':
        bot.send_message(message.chat.id, 'Отлично! У вас все шансы на победу! '
                                          'Нажмите кнопку, чтобы начать игру:', reply_markup=markup)
    elif read.lower() == 'нет':
        bot.send_message(message.chat.id, 'Вы обязательно справитесь! '
                                          'Нажмите кнопку, чтобы начать игру:', reply_markup=markup)


# словарь, где ключ - выбранное предложение
# а значение - информация о том, сгенерированное оно(computer) или оригинальноe(tolstoy)
current_questions = {}
user_scores = 0  # cчетчик очков


# функция запускается только при нажатии кнопки "начать" и отсылает к функции, которая содержит саму игру
@bot.callback_query_handler(func=lambda callback: callback.data == 'game')
def sentences(callback):
    global user_scores
    user_scores = 0  # обнуляем user_scores перед началом новой игры
    start_new_round(callback.message.chat.id, 10)


# функция с реализацией самой игры
def start_new_round(chat_id, attempts):
    # рандомно выбирается, какой текст будет предлагаться пользователю - сгенерированный или оригинальный
    choice = random.choice(['text', 'markov'])
    # если выбирается оригинальный текст, то далее выбираем рандомное предложение из него
    # и заносим в словарь с информацией о том, что предложение из произведения Толстого
    if choice == 'text':
        generated_text = random.choice(text.split('.')).strip()
        current_questions[chat_id] = {'sentence': generated_text, 'source': 'tolstoy'}
    # то же самое происходит и с сгенерированным предложением
    else:
        generated_text = text_model.make_sentence().strip()
        current_questions[chat_id] = {'sentence': generated_text, 'source': 'computer'}
    # пользователь выбирает ответ с помощью соответствующих кнопок
    markup = types.ReplyKeyboardMarkup()
    btn1 = types.KeyboardButton('Толстой')
    btn2 = types.KeyboardButton('Компьютер')
    markup.row(btn1, btn2)
    bot.send_message(chat_id, generated_text, reply_markup=markup)
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: check_answer(message, attempts))


# функция, которая проверяет, правильно или нет ответил пользователь, и считает баллы
def check_answer(message, attempts):
    global user_scores
    user_response = message.text.strip().lower()
    chat_id = message.chat.id
    if chat_id in current_questions:
        correct_answer = current_questions[chat_id]['source']

        # удаление информации о вопросе
        del current_questions[chat_id]

        attempts -= 1

        if (user_response == 'толстой' and correct_answer == 'tolstoy') or (user_response == 'компьютер' and correct_answer == 'computer'):
            bot.send_message(chat_id, "Правильно! +1 балл.")
            user_scores += 1
            # обновляем счет в базе данных
            conn = sqlite3.connect('results.sql')
            cur = conn.cursor()
            cur.execute("UPDATE users SET score = score + 1 WHERE name = ?", (name,))
            conn.commit()
            cur.close()
            conn.close()

        else:
            bot.send_message(chat_id, "Неправильно! Вы не получаете балл")

        # отправляем обновленный счет
        bot.send_message(chat_id, f"Ваш счет: {user_scores}")
        if attempts > 0:
            start_new_round(message.chat.id, attempts)

        else:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton('Таблица лидеров', callback_data='stats'))
            bot.send_message(chat_id, f"Поздравляю! Игра закончена! Ваш результат: {user_scores}", reply_markup=markup)


# функция для подсчета статистики
@bot.callback_query_handler(func=lambda callback: callback.data == 'stats')
def stats(callback):
    conn = sqlite3.connect('results.sql')
    cur = conn.cursor()

    # извлекаем топ-3 пользователей, которые набрали наибольшее количество очков
    cur.execute("SELECT name, score FROM users ORDER BY score DESC LIMIT 3")
    top_users = cur.fetchall()
    # извлекаем общее количество игроков
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]

    # формулируем и отправляем сообщения с результатами по базе данных
    message = f"Всего игроков: {total_users}\nТоп-3 пользователей по количеству набранных очков:\n"
    for user, score in top_users:
        message += f"{user} - {score} очков\n"

    bot.send_message(callback.message.chat.id, message)

    # закрываем соединение с базой данных
    cur.close()
    conn.close()


bot.polling(none_stop=True)

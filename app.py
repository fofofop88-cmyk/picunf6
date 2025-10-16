from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime
import hashlib
import json
import os
import requests

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here_change_this_in_production'
socketio = SocketIO(app, cors_allowed_origins="*")

# Конфигурация Telegram бота
TELEGRAM_BOT_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN_HERE'
TELEGRAM_CHANNEL_ID = '@YOUR_CHANNEL_USERNAME_HERE'  # или ID канала

# Простая "база данных" пользователей
users_db = {
    'admin': {
        'password': '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8',  # password
        'username': 'admin'
    }
}

# Хранилище активных пользователей
active_users = {}
messages = []
support_tickets = []  # Хранилище обращений в поддержку

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def send_to_telegram(message):
    """Отправка сообщения в Telegram канал"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHANNEL_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")
        return False

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('chat'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username in users_db and users_db[username]['password'] == hash_password(password):
            session['user'] = users_db[username]
            session['username'] = username
            return redirect(url_for('chat'))
        else:
            return render_template('login.html', error='Неверное имя пользователя или пароль')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if len(username) < 3:
            return render_template('register.html', error='Имя пользователя должно быть не менее 3 символов')
        if len(password) < 4:
            return render_template('register.html', error='Пароль должен быть не менее 4 символов')
        if password != confirm_password:
            return render_template('register.html', error='Пароли не совпадают')
        if username in users_db:
            return render_template('register.html', error='Пользователь уже существует')
        
        users_db[username] = {
            'password': hash_password(password),
            'username': username
        }
        
        session['user'] = users_db[username]
        session['username'] = username
        return redirect(url_for('chat'))
    
    return render_template('register.html')

@app.route('/chat')
def chat():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('chat.html', username=session['username'])

@app.route('/support', methods=['GET', 'POST'])
def support():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        issue_type = request.form['issue_type']
        title = request.form['title']
        description = request.form['description']
        priority = request.form['priority']
        
        # Создаем обращение
        ticket = {
            'id': len(support_tickets) + 1,
            'username': session['username'],
            'issue_type': issue_type,
            'title': title,
            'description': description,
            'priority': priority,
            'status': 'new',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'admin_response': None
        }
        
        support_tickets.append(ticket)
        
        # Отправляем уведомление в Telegram
        telegram_message = f"""
🆕 <b>НОВОЕ ОБРАЩЕНИЕ В ПОДДЕРЖКУ</b>

👤 <b>Пользователь:</b> {session['username']}
📋 <b>Тип проблемы:</b> {issue_type}
🚨 <b>Приоритет:</b> {priority}
📝 <b>Заголовок:</b> {title}
📄 <b>Описание:</b> {description}
⏰ <b>Время:</b> {ticket['timestamp']}
🆔 <b>ID обращения:</b> #{ticket['id']}
        """.strip()
        
        send_to_telegram(telegram_message)
        
        return render_template('support.html', 
                             success='Ваше обращение отправлено! Мы ответим в ближайшее время.',
                             username=session['username'])
    
    return render_template('support.html', username=session['username'])

@app.route('/support/tickets')
def support_tickets_list():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    user_tickets = [t for t in support_tickets if t['username'] == session['username']]
    return render_template('support_tickets.html', 
                         tickets=user_tickets, 
                         username=session['username'])

@app.route('/admin/support')
def admin_support():
    if 'user' not in session or session['username'] != 'admin':
        return "Доступ запрещен", 403
    
    return render_template('admin_support.html', 
                         tickets=support_tickets,
                         username=session['username'])

@app.route('/admin/support/respond', methods=['POST'])
def admin_respond():
    if 'user' not in session or session['username'] != 'admin':
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    ticket_id = int(request.form['ticket_id'])
    response = request.form['response']
    
    for ticket in support_tickets:
        if ticket['id'] == ticket_id:
            ticket['status'] = 'answered'
            ticket['admin_response'] = response
            ticket['answered_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Отправляем ответ в Telegram
            telegram_message = f"""
✅ <b>ОТВЕТ НА ОБРАЩЕНИЕ</b>

👤 <b>Пользователь:</b> {ticket['username']}
🆔 <b>ID обращения:</b> #{ticket['id']}
📝 <b>Заголовок:</b> {ticket['title']}
💬 <b>Ответ администратора:</b> {response}
⏰ <b>Время ответа:</b> {ticket['answered_at']}
            """.strip()
            
            send_to_telegram(telegram_message)
            break
    
    return jsonify({'success': True})

@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('username', None)
    return redirect(url_for('login'))

@socketio.on('connect')
def handle_connect():
    if 'username' in session:
        user_data = {
            'username': session['username'],
            'sid': request.sid,
            'join_time': datetime.now().strftime('%H:%M:%S')
        }
        active_users[request.sid] = user_data
        
        print(f'Пользователь подключился: {session["username"]}')
        
        emit('user_connected', {
            'username': session['username'],
            'online_users': get_online_users(),
            'timestamp': get_current_time()
        }, broadcast=True)
        
        emit('message_history', messages)
        emit('online_users_update', get_online_users())

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in active_users:
        username = active_users[request.sid]['username']
        del active_users[request.sid]
        
        print(f'Пользователь отключился: {username}')
        
        emit('user_disconnected', {
            'username': username,
            'online_users': get_online_users(),
            'timestamp': get_current_time()
        }, broadcast=True)

@socketio.on('send_message')
def handle_message(data):
    if 'username' not in session:
        return
    
    username = session['username']
    message_data = {
        'id': len(messages) + 1,
        'username': username,
        'message': data['message'],
        'timestamp': get_current_time(),
        'type': 'message'
    }
    
    messages.append(message_data)
    
    if len(messages) > 100:
        messages.pop(0)
    
    emit('new_message', message_data, broadcast=True)
    
    print(f'Сообщение от {username}: {data["message"]}')

@socketio.on('typing')
def handle_typing(data):
    if 'username' not in session:
        return
    
    username = session['username']
    emit('user_typing', {
        'username': username,
        'is_typing': data['is_typing']
    }, broadcast=True, include_self=False)

def get_online_users():
    return [user['username'] for user in active_users.values()]

def get_current_time():
    return datetime.now().strftime('%H:%M:%S')

# Добавьте в конец app.py
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)

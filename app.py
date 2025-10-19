from flask import Flask, render_template, request, session, redirect, url_for, jsonify, send_from_directory
from datetime import datetime, timedelta
import hashlib
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'

# ========== КОНФИГУРАЦИЯ АДМИНА ==========
ADMIN_USERNAME = "superadmin"    # ИЗМЕНИТЕ НА СВОЕ ИМЯ
ADMIN_PASSWORD = "MyPassword123" # ИЗМЕНИТЕ НА СВОЙ ПАРОЛЬ
# =========================================

# Функции
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def is_banned(username):
    if username in banned_users:
        ban_data = banned_users[username]
        if ban_data['banned_until'] and datetime.now() > ban_data['banned_until']:
            del banned_users[username]
            return False
        return True
    return False

def get_user_role(username):
    return users_db.get(username, {}).get('role', 'user')

def can_ban(admin_username, target_username):
    admin_role = get_user_role(admin_username)
    target_role = get_user_role(target_username)
    if admin_role == 'admin' and target_role != 'admin':
        return True
    elif admin_role == 'moderator' and target_role == 'user':
        return True
    return False

# Делаем функцию доступной в шаблонах
@app.context_processor
def utility_processor():
    return dict(get_user_role=get_user_role)

# Базы данных
users_db = {
    ADMIN_USERNAME: {
        'password': hash_password(ADMIN_PASSWORD),
        'username': ADMIN_USERNAME,
        'role': 'admin'
    }
}

banned_users = {}
warnings = {}
messages = []
active_users = []
support_tickets = []

# PWA маршруты
@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/service-worker.js')
def service_worker():
    return send_from_directory('static', 'service-worker.js')

# Основные маршруты
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
        
        if is_banned(username):
            ban_data = banned_users[username]
            return render_template('login.html', error=f'Вы забанены до {ban_data["banned_until"].strftime("%d.%m.%Y %H:%M")}. Причина: {ban_data["reason"]}')
        
        if username in users_db and users_db[username]['password'] == hash_password(password):
            session['user'] = users_db[username]
            session['username'] = username
            
            if username not in active_users:
                active_users.append(username)
                
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
        
        if username.lower() == ADMIN_USERNAME.lower():
            return render_template('register.html', error='Это имя пользователя зарезервировано')
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
            'username': username,
            'role': 'user'
        }
        
        session['user'] = users_db[username]
        session['username'] = username
        return redirect(url_for('chat'))
    
    return render_template('register.html')

@app.route('/chat')
def chat():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    user_role = get_user_role(username)
    
    return render_template('chat.html', 
                         username=username,
                         user_role=user_role,
                         messages=messages[-20:],
                         online_users=active_users)

@app.route('/send_message', methods=['POST'])
def send_message():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    username = session['username']
    
    if is_banned(username):
        return jsonify({'error': 'Вы забанены и не можете отправлять сообщения'}), 403
    
    message_text = request.form.get('message', '').strip()
    
    if message_text:
        message_data = {
            'id': len(messages) + 1,
            'username': username,
            'message': message_text,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }
        messages.append(message_data)
        
        if len(messages) > 100:
            messages.pop(0)
            
        return jsonify({'success': True})
    
    return jsonify({'error': 'Empty message'}), 400

@app.route('/get_messages')
def get_messages():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    return jsonify(messages[-20:])

@app.route('/get_online_users')
def get_online_users():
    return jsonify(active_users)

# Система поддержки
@app.route('/support', methods=['GET', 'POST'])
def support():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        issue_type = request.form['issue_type']
        title = request.form['title']
        description = request.form['description']
        priority = request.form['priority']
        
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
        return render_template('support.html', 
                             success='Ваше обращение отправлено!',
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

# Система банов
@app.route('/admin/ban', methods=['POST'])
def ban_user():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    admin_username = session['username']
    target_username = request.form.get('username')
    reason = request.form.get('reason', 'Нарушение правил')
    duration_hours = int(request.form.get('duration', 24))
    
    if not target_username:
        return jsonify({'error': 'Username required'}), 400
    
    if not can_ban(admin_username, target_username):
        return jsonify({'error': 'Недостаточно прав'}), 403
    
    banned_until = datetime.now() + timedelta(hours=duration_hours)
    banned_users[target_username] = {
        'reason': reason,
        'banned_by': admin_username,
        'banned_until': banned_until,
        'banned_at': datetime.now()
    }
    
    if target_username in active_users:
        active_users.remove(target_username)
    
    messages.append({
        'id': len(messages) + 1,
        'username': '🔨 Система',
        'message': f'Пользователь {target_username} забанен до {banned_until.strftime("%d.%m.%Y %H:%M")}. Причина: {reason}',
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'type': 'system'
    })
    
    return jsonify({
        'success': True,
        'message': f'Пользователь {target_username} забанен на {duration_hours} часов'
    })

@app.route('/admin/unban', methods=['POST'])
def unban_user():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    admin_username = session['username']
    target_username = request.form.get('username')
    
    if not target_username:
        return jsonify({'error': 'Username required'}), 400
    
    admin_role = get_user_role(admin_username)
    if admin_role not in ['admin', 'moderator']:
        return jsonify({'error': 'Недостаточно прав'}), 403
    
    if target_username in banned_users:
        del banned_users[target_username]
        
        messages.append({
            'id': len(messages) + 1,
            'username': '🔓 Система',
            'message': f'Пользователь {target_username} разбанен',
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'type': 'system'
        })
        
        return jsonify({'success': True, 'message': f'Пользователь {target_username} разбанен'})
    else:
        return jsonify({'error': 'Пользователь не забанен'}), 404

@app.route('/admin/warn', methods=['POST'])
def warn_user():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    admin_username = session['username']
    target_username = request.form.get('username')
    reason = request.form.get('reason', 'Предупреждение')
    
    if not target_username:
        return jsonify({'error': 'Username required'}), 400
    
    if not can_ban(admin_username, target_username):
        return jsonify({'error': 'Недостаточно прав'}), 403
    
    if target_username not in warnings:
        warnings[target_username] = 0
    warnings[target_username] += 1
    
    warning_count = warnings[target_username]
    
    if warning_count >= 3:
        banned_until = datetime.now() + timedelta(hours=24)
        banned_users[target_username] = {
            'reason': f'Автоматический бан после {warning_count} предупреждений',
            'banned_by': 'system',
            'banned_until': banned_until,
            'banned_at': datetime.now()
        }
        warnings[target_username] = 0
        
        message = f'Пользователь {target_username} автоматически забанен на 24 часа за {warning_count} предупреждения'
    else:
        message = f'Пользователь {target_username} получил предупреждение ({warning_count}/3). Причина: {reason}'
    
    messages.append({
        'id': len(messages) + 1,
        'username': '⚠️ Система',
        'message': message,
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'type': 'system'
    })
    
    return jsonify({'success': True, 'message': message, 'warnings': warning_count})

@app.route('/admin/banned_users')
def get_banned_users():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    username = session['username']
    user_role = get_user_role(username)
    
    if user_role not in ['admin', 'moderator']:
        return jsonify({'error': 'Недостаточно прав'}), 403
    
    banned_list = []
    for banned_user, ban_data in banned_users.items():
        banned_list.append({
            'username': banned_user,
            'reason': ban_data['reason'],
            'banned_by': ban_data['banned_by'],
            'banned_until': ban_data['banned_until'].strftime('%d.%m.%Y %H:%M') if ban_data['banned_until'] else 'Навсегда',
            'banned_at': ban_data['banned_at'].strftime('%d.%m.%Y %H:%M')
        })
    
    return jsonify(banned_list)

@app.route('/admin/users')
def get_all_users():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    username = session['username']
    user_role = get_user_role(username)
    
    if user_role not in ['admin', 'moderator']:
        return jsonify({'error': 'Недостаточно прав'}), 403
    
    users_list = []
    for user, data in users_db.items():
        users_list.append({
            'username': user,
            'role': data.get('role', 'user'),
            'is_online': user in active_users,
            'warnings': warnings.get(user, 0),
            'is_banned': is_banned(user)
        })
    
    return jsonify(users_list)

@app.route('/admin/panel')
def admin_panel():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    username = session['username']
    user_role = get_user_role(username)
    
    if user_role not in ['admin', 'moderator']:
        return "Доступ запрещен", 403
    
    return render_template('admin_panel.html', 
                         username=username,
                         user_role=user_role,
                         online_users=active_users)

@app.route('/logout')
def logout():
    username = session.get('username')
    if username in active_users:
        active_users.remove(username)
    session.pop('user', None)
    session.pop('username', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
